# ASCON Basys3 Desktop Console

Python/Tkinter app with separate UI, packet, serial, and transaction modules. Inputs are on the left; returned results are on the right. Supports encryption and authenticated decryption using the included UART v2 bridge.

## Run on Windows

Install Python 3.10+ with Tcl/Tk support (included with the standard python.org installer). Extract this folder and open a terminal in it:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

On Ubuntu, install python3-tk and python3-venv, create the environment with `python3 -m venv .venv`, then use `.venv/bin/python` for pip and main.py. The only pip dependency is pyserial. The Python reference is included for the optional software demo.

## Try without hardware

Choose Software demo, Connect, then Send & encrypt. Results are explicitly labeled SOFTWARE DEMO; this does not use an FPGA. Click Load this result for decryption, then Send & decrypt to recover the plaintext. This same workflow works with FPGA hardware after installing the updated bridge below.

## Install the FPGA update

Encryption uses the previous corrected 68-byte request and 34-byte response. Decryption requires the protocol module in THIS package.

1. Replace your existing ascon_uart_protocol.v with fpga/ascon_uart_protocol.v. Keep only one definition in Vivado. Keep the existing ASCON core, corrected top/UART files, and matching basys3_master.xdc.
2. Add fpga/tb_ascon_uart_v2.v as a Simulation Source; select tb_ascon_uart_v2 as simulation top. Launch behavioral simulation and enter `run all`. Expect 47 passing encryption/decryption/authentication tests.
3. To rerun the 302-case encryption regression, replace your previous testbench with fpga/tb_ascon_basys3_top.v, select tb_ascon_basys3_top and enter `run all`. Its invalid-command test now uses 7F: the previous test used 02, which is now a valid decrypt command.
4. Set ascon_basys3_top as design top. Synthesize, implement, check timing/DRC, generate a bitstream and program Basys3.
5. Press/release center button btnC. Do not press the separate PROG configuration-reset button.
6. Connect through the PROG micro-USB connector, select FPGA hardware and the correct COM port, then Connect. Close other serial terminals using that port. The app uses 115200, 8N1, no flow control.

The accelerated simulation baud override is testbench-only; keep hardware defaults at 100 MHz / 115200 baud. Hardware operation and Vivado implementation/timing still need checking on your board.

## One USB cable carries both directions

The board's PROG micro-USB port is shared by JTAG programming and UART through its onboard bridge. UART RX and TX are separate signals, so the same COM connection can read and write. Electrically it supports full duplex; this protocol uses sequential request/response: send all input bytes, wait for all 34 output bytes, then start another operation. The FPGA does not queue requests while busy.

Basys3 also has a USB-A host connector for peripherals. It is not a second PC UART output for this design. To give results to another PC, use Export result JSON and transfer the file. A network relay through the first PC or a separate 3.3 V USB-UART adapter on Pmod pins could be added later; neither is implemented here. A second direct serial connection would require RTL/XDC changes.

To decrypt, a recipient needs the same algorithm, secret key, nonce, AD, ciphertext and tag. Export includes nonce/AD/ciphertext/tag but excludes the secret key and plaintext; provide the key separately. Exporting does not automatically transmit anything across a network. Another PC can read the JSON without a board and can decrypt with compatible software or FPGA logic.

Sources:
- https://digilent.com/reference/_media/basys3:basys3_rm.pdf
- https://pyserial.readthedocs.io/en/latest/pyserial_api.html

## Defaults and input behavior

| Input | Default |
|---|---|
| Key | 000102030405060708090a0b0c0d0e0f (lab example) |
| Encryption nonce | Fresh random 16-byte nonce on every send |
| Associated data | ASCON |
| Plaintext | hello FPGA |
| Decryption sample nonce | 101112131415161718191a1b1c1d1e1f |
| Decryption sample ciphertext | 41526d4d50689585ea2d |
| Decryption sample tag | 722172428e2b0f85e3a7cd2f7845572e |

The decrypt sample uses the default key and AD and recovers hello FPGA. All fields are editable. Blank fields fall back to these defaults. Tick Use empty AD / Use empty input data for actual zero-length fields. The nonce used in an operation is displayed with its result. Leave fresh random nonce enabled for encryption; manual nonce entry is useful for known test vectors, but do not reuse a nonce for new messages with the same key.

Key, nonce, tag and decryption ciphertext are always hexadecimal. The encoding dropdown controls AD and encryption plaintext. Blank AD/plaintext in hex mode still means the same default bytes. Input limits are 16 BYTES each, not 16 characters; UTF-8 Sinhala text may use several bytes per character.

Changing operation loads that operation's sample values. Load this result for decryption instead copies the exact previous encryption inputs/result, including its original nonce and key. A nonce must not be changed when decrypting an existing ciphertext.

Ciphertext is shown as hex because it is binary. Verified plaintext is shown as hex and UTF-8 when valid. The key on the left is a local input; the FPGA never returns it. A successful encryption response means a tag was generated; it does not independently prove the hardware computation against a software reference. A successful decryption response means the core reported tag verification success.

## Code reading order

| File | Responsibility |
|---|---|
| main.py | Starts the app |
| ascon_app/ui.py | Widgets, actions, worker thread, result display |
| ascon_app/protocol.py | Defaults, validation, packet encoding/decoding |
| ascon_app/transport.py | Port discovery, serial I/O, timeouts, demo transport |
| ascon_app/service.py | Runs a transaction and exports a result |
| ascon_app/reference_ascon.py | Supplied reference implementation, demo only |
| fpga/ascon_uart_protocol.v | FPGA bridge with commands 01 and 02 |
| fpga/tb_ascon_uart_v2.v | Decryption/authentication plus encryption tests |
| fpga/tb_ascon_basys3_top.v | Existing encryption regression with updated invalid command |
| tests/test_app.py | Python validation, packet, transport and export tests |

Tkinter runs on the main thread. Serial I/O runs on a worker and reports through a queue, keeping the window responsive. Controls prevent simultaneous requests. There is no automatic transaction retry.

## UART v2 contract

| Field | Encrypt | Decrypt |
|---|---|---|
| Marker | A5 | A5 |
| Command | 01 | 02 |
| AD length | 1 byte, 0..16 | 1 byte, 0..16 |
| Data length | Plaintext bytes, 0..16 | Ciphertext bytes, 0..16 |
| Key | 16 bytes | 16 bytes |
| Nonce | 16 bytes | 16 bytes |
| AD | 16-byte field, zero-padded | 16-byte field, zero-padded |
| Data | 16-byte padded plaintext | 16-byte padded ciphertext |
| Input tag | Absent | 16 bytes |
| Total | 68 bytes | 84 bytes |

External fields use natural byte order. The RTL does the core-specific key/nonce/tag repacking. The command byte drives `ascon_decrypt <= (command == 8'h02)` in START; the wire itself is not transmitted.

Response is always `5A STATUS DATA[16] TAG[16]`, 34 bytes. DATA holds ciphertext for encryption or authenticated plaintext for decryption. Bytes after the data length are zero.

- 00: success.
- 01: unsupported command.
- 02: invalid AD/data length.
- 03: authentication failure.

All error responses have 32 zero payload bytes. Successful decryption returns the computed tag. Candidate plaintext is buffered inside the bridge until `done`; if `auth_ok` is false it is cleared before any UART output. This prevents unauthenticated plaintext release through this UART interface.

Unknown commands use a 68-byte request; command 02 always uses 84 bytes, including invalid-length requests. Send binary bytes, not ASCII hex text.

## Recovery and limits

On timeout/invalid response, the app closes its serial connection and clears the successful result. Press btnC, reconnect and resend. The FPGA has no packet timeout/CRC, so a truncated packet cannot be repaired reliably simply by sending another A5. Authentication failure also closes the connection; correct the inputs and reconnect. The app's default response deadline is 3 seconds.

Round-trip time includes Python, USB, UART and FPGA processing; it is not core-only latency. Demo timing is software timing. The UART bridge still accepts only 0..16 bytes each of AD and data, even though the underlying core supports more.

Run Python tests:

```sh
python -m unittest discover -s tests -v
```

Verification logs are in verification/. Tests cover Python logic, the live Tkinter software-demo workflow and behavioral Verilog simulation. No physical Basys3/COM-port test or Vivado implementation was possible here. The app's Windows appearance may differ from the Linux preview. The reference implementation retains its supplied CC0 license in REFERENCE_LICENSE.txt.
