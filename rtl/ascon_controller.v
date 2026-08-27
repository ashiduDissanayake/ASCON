// ascon_controller: top-level FSM orchestrating Ascon-AEAD128 encryption and
// decryption on top of the already-verified submodules in rtl/.
//
// This is the "state owner": it drives ascon_permutation (instantiated twice,
// once per round count -- see below), performs the key/nonce loading,
// associated-data absorption, plaintext/ciphertext processing, and
// finalization/tag steps of NIST SP 800-232 Ascon-AEAD128, matching
// model/refmodel.py + pyascon/ascon.py bit-for-bit. The exact block-boundary
// and padding behaviour (including the "extra all-pad block" case for
// AD/PT/CT lengths that are an exact multiple of the 16-byte rate, and the
// AD-vs-PT/CT permute-cadence difference: every AD block -- including the
// synthetic extra one -- is followed by a b-round permute, whereas PT/CT's
// final block is not) was cross-checked against pyascon for a wide range of
// AD/PT lengths (0, partial, exact-multiple, multi-block) before this RTL
// was written; see the per-state comments below for how each case maps to
// a state transition.
//
// ROUND COUNTS
//   Ascon-AEAD128 uses a=12 rounds for initialization/finalization and
//   b=8 rounds for the intermediate AD/PT/CT permutes. ascon_permutation's
//   ROUNDS is an elaboration-time parameter, not a runtime input, so this
//   controller instantiates it twice -- u_perm_a (ROUNDS=12) and
//   u_perm_b (ROUNDS=8) -- and only ever pulses `start` on the one needed
//   for the current phase. Both share the same state_in (state_reg); only
//   one is ever running at a time.
//
// BUS / BYTE-ORDERING CONVENTIONS
//   - `key`, `nonce`, and `tag_out`/`tag_in` are packed word-first-in-
//     high-bits, exactly like ascon_keyxor's `key` port and
//     ascon_permutation's state bus: bits [127:64] hold the value's first
//     8 bytes (as a little-endian 64-bit word, matching pyascon's
//     bytes_to_int), bits [63:0] hold the next 8 bytes. For the tag,
//     bits [127:64] = S3, bits [63:0] = S4 after finalization.
//   - `ad_data` / `pc_data_in` / `pc_data_out`, by contrast, are packed
//     byte-serially: bit range [8*i +: 8] holds stream byte `i` of the
//     current (up to) 16-byte block, i = 0 (first byte) .. 15 (last
//     byte). This is the convention ascon_pad.v's `valid_bytes` already
//     assumes (the pad byte lands at position `valid_bytes` counting from
//     bit 0), so a block's two 64-bit rate words are word0 = data[63:0],
//     word1 = data[127:64].
//
// INTERFACE
//   AD and PT/CT are each presented as a byte length (in bytes) plus a
//   128-bit-wide ready/valid beat stream; the controller derives per-beat
//   validity, padding, and "last real block" behaviour from the byte
//   length counters itself, so callers never need to compute padding or
//   assert an external "last" flag. AD/PT lengths of 0 are handled without
//   requiring any beat on that stream at all.
//
// WHY THIS ISN'T WRAPPED IN ascon_io_if
//   ad_ready/ad_valid, pc_ready/pc_valid, and pc_valid_out/pc_ready_in
//   above are already a native, correctly-handshaked ready/valid interface
//   driven straight off the FSM -- there's no separate internal "IO
//   holding register" here duplicating what ascon_io_if.v does. ascon_io_if
//   is a one-slot skid buffer meant to sit *outside* a core like this one
//   (see its own header), e.g. as the register slice inside an
//   AXI-Stream/Avalon-ST adapter wrapping ascon_controller for a specific
//   bus, or to decouple this core's timing from an upstream/downstream
//   block on a different clock-enable schedule. Instantiating it on these
//   ports internally would only add a redundant pipeline stage with no
//   corresponding logic being replaced, so it's left as a standalone
//   building block for that future adapter rather than forced in here.
//   ascon_pad.v, by contrast, genuinely was being reimplemented inline
//   (the single-line "insert 0x01 at byte `valid`" case in
//   ad_lane_update/pc_lane_update) and is now instantiated for real; see
//   u_ad_pad/u_pc_pad below.
module ascon_controller (
    input  wire         clk,
    input  wire         rst_n,

    // Control / configuration -------------------------------------------------
    input  wire         start,        // pulse for 1 cycle to begin a new op
    input  wire         decrypt,      // 0 = encrypt, 1 = decrypt+verify
    input  wire [127:0] key,          // key[127:64]=bytes0-7, key[63:0]=bytes8-15
    input  wire [127:0] nonce,        // same convention as key
    input  wire [31:0]  ad_len,       // associated-data length, bytes
    input  wire [31:0]  pc_len,       // plaintext (encrypt) / ciphertext (decrypt)
                                       // length, bytes -- excludes the 16-byte tag
    input  wire [127:0] tag_in,       // expected tag, decrypt mode only; same
                                       // convention as tag_out

    output reg          busy,
    output reg          done,         // 1-cycle pulse: operation complete;
                                       // tag_out/auth_ok are valid this cycle
    output reg          auth_ok,      // decrypt mode only, valid at `done`:
                                       // 1 = tag matched, 0 = tag mismatch
    output reg  [127:0] tag_out,      // computed tag, valid at `done`

    // Associated-data input stream (skip entirely when ad_len == 0) ----------
    output reg           ad_ready,
    input  wire          ad_valid,
    input  wire [127:0]  ad_data,

    // Plaintext/ciphertext input stream ---------------------------------------
    output reg           pc_ready,
    input  wire          pc_valid,
    input  wire [127:0]  pc_data_in,

    // Ciphertext/plaintext output stream --------------------------------------
    output reg           pc_valid_out,
    input  wire          pc_ready_in,
    output reg  [127:0]  pc_data_out,
    output reg  [4:0]    pc_bytes_out, // valid bytes in pc_data_out this beat
    output reg           pc_last_out   // 1 on the final output beat
);

    // ------------------------------------------------------------------
    // Ascon-AEAD128 constant: IV = bytes([1,0,0x8C,0x80,0,0x10,0,0]) packed
    // the same little-endian way as every other 64-bit state word (see
    // model/refmodel.py::encrypt's trace branch, which builds this from
    // version=1, k=128, rate=16, a=12, b=8, taglen=128).
    // ------------------------------------------------------------------
    localparam [63:0] ASCON_IV = 64'h00001000808c0001;

    // ------------------------------------------------------------------
    // State register: S0..S4, 320 bits, MSB-first (matches
    // ascon_permutation's state_in/state_out layout).
    // ------------------------------------------------------------------
    reg [319:0] state_reg;
    wire [63:0] s0 = state_reg[319:256];
    wire [63:0] s1 = state_reg[255:192];
    wire [63:0] s2 = state_reg[191:128];
    wire [63:0] s3 = state_reg[127:64];
    wire [63:0] s4 = state_reg[63:0];

    reg [127:0] key_reg, nonce_reg, tag_in_reg;
    reg         decrypt_reg;
    reg [31:0]  ad_remaining, pc_remaining;
    reg         ad_extra_pending, pc_extra_pending, pc_final;
    reg [127:0] pc_data_reg;

    wire [63:0] key_w0 = key_reg[127:64];
    wire [63:0] key_w1 = key_reg[63:0];

    // ------------------------------------------------------------------
    // Padding: delegated to ascon_pad instead of duplicating the "insert
    // 0x01 at the first empty byte position" rule inline. One instance per
    // stream (AD, PC) is enough -- both are pure combinational lookups, so
    // it's fine that each is "computed" every cycle even in states where
    // its result isn't consulted.
    //
    // valid_bytes for each stream is derived straight from *_remaining, so
    // this is correct in every state that reads it, including the
    // synthetic all-pad S_AD_EXTRA/S_PC_EXTRA blocks: by construction
    // those states are only ever entered once *_remaining has already
    // dropped to 0 (see S_AD_WAIT/S_PC_ABSORB below), which makes
    // ad_valid_bytes_w/pc_valid_bytes_w evaluate to 0 there automatically
    // -- no separate zero-literal call site needed. Bytes beyond
    // valid_bytes are masked out downstream in ad_lane_update/
    // pc_lane_update regardless of what ascon_pad leaves in that range, so
    // ad_data/pc_data_reg holding a stale beat during those states is
    // harmless.
    // ------------------------------------------------------------------
    wire [4:0]   ad_valid_bytes_w = (ad_remaining >= 32'd16) ? 5'd16 : ad_remaining[4:0];
    wire [127:0] ad_padded_w;
    ascon_pad u_ad_pad (
        .data_in    (ad_data),
        .valid_bytes(ad_valid_bytes_w),
        .padded_out (ad_padded_w)
    );

    wire [4:0]   pc_valid_bytes_w = (pc_remaining >= 32'd16) ? 5'd16 : pc_remaining[4:0];
    wire [127:0] pc_padded_w;
    ascon_pad u_pc_pad (
        .data_in    (pc_data_reg),
        .valid_bytes(pc_valid_bytes_w),
        .padded_out (pc_padded_w)
    );

    // ------------------------------------------------------------------
    // ascon_permutation instances: ROUNDS is elaboration-time only, so we
    // instantiate both round counts Ascon-AEAD128 needs and only pulse the
    // one relevant to the current phase.
    // ------------------------------------------------------------------
    reg          perm_a_start, perm_b_start;
    wire         perm_a_done, perm_b_done;
    wire [319:0] perm_a_out, perm_b_out;

    ascon_permutation #(.ROUNDS(12)) u_perm_a (
        .clk      (clk),
        .rst_n    (rst_n),
        .start    (perm_a_start),
        .state_in (state_reg),
        .state_out(perm_a_out),
        .done     (perm_a_done)
    );

    ascon_permutation #(.ROUNDS(8)) u_perm_b (
        .clk      (clk),
        .rst_n    (rst_n),
        .start    (perm_b_start),
        .state_in (state_reg),
        .state_out(perm_b_out),
        .done     (perm_b_done)
    );

    // ------------------------------------------------------------------
    // Post-initialization key XOR: reuses ascon_keyxor.v as-is, since its
    // fixed x3/x4 mapping is exactly the pattern Ascon-AEAD128 uses right
    // after the first 12-round permutation.
    // ------------------------------------------------------------------
    wire [63:0] initxor_x0, initxor_x1, initxor_x2, initxor_x3, initxor_x4;
    ascon_keyxor u_init_keyxor (
        .x0_in(s0), .x1_in(s1), .x2_in(s2), .x3_in(s3), .x4_in(s4),
        .key  (key_reg),
        .x0_out(initxor_x0), .x1_out(initxor_x1), .x2_out(initxor_x2),
        .x3_out(initxor_x3), .x4_out(initxor_x4)
    );

    // ------------------------------------------------------------------
    // AD absorption helper: rate-word (S0,S1) update for one <=16-byte
    // block, by byte lane, in the ad_data/pc_data stream-order convention
    // (bit [8*i +: 8] = stream byte i). `padded_data` is ascon_pad's
    // output (real payload for i<valid, the 0x01 pad byte at i==valid);
    // bytes beyond that (i>valid) are left untouched regardless of what
    // ascon_pad passes through there. AD absorption is always the
    // "new = old ^ payload" direction, matching
    // ascon_process_associated_data.
    // ------------------------------------------------------------------
    function automatic [127:0] ad_lane_update;
        input [127:0] s_old;        // {S1(bytes8-15), S0(bytes0-7)}, stream order
        input [127:0] padded_data;  // ascon_pad(data, valid), same convention
        input [4:0]   valid;
        integer i;
        reg [7:0] sb, db, nb;
        reg [127:0] out;
        begin
            for (i = 0; i < 16; i = i + 1) begin
                sb = s_old[i*8 +: 8];
                db = padded_data[i*8 +: 8];
                if (i <= valid)
                    nb = sb ^ db;
                else
                    nb = sb;
                out[i*8 +: 8] = nb;
            end
            ad_lane_update = out;
        end
    endfunction

    // ------------------------------------------------------------------
    // PT/CT absorption helper: like ad_lane_update, but direction-aware
    // (encrypt: new = old^payload, out = new; decrypt: new = payload,
    // out = old^payload), matching ascon_process_plaintext /
    // ascon_process_ciphertext. Returns {new_s(128), out(128)}.
    // ------------------------------------------------------------------
    function automatic [255:0] pc_lane_update;
        input [127:0] s_old;
        input [127:0] padded_data;  // ascon_pad(data, valid)
        input [4:0]   valid;
        input         dec;
        integer i;
        reg [7:0] sb, db, nb, ob;
        reg [127:0] s_new, out;
        begin
            for (i = 0; i < 16; i = i + 1) begin
                sb = s_old[i*8 +: 8];
                db = padded_data[i*8 +: 8];
                if (i < valid) begin
                    if (dec) begin
                        nb = db;
                        ob = sb ^ db;
                    end else begin
                        nb = sb ^ db;
                        ob = nb;
                    end
                end else if (i == valid) begin
                    nb = sb ^ db;  // db == 8'h01, the pad byte from ascon_pad
                    ob = 8'h00;
                end else begin
                    nb = sb;
                    ob = 8'h00;
                end
                s_new[i*8 +: 8] = nb;
                out[i*8 +: 8]   = ob;
            end
            pc_lane_update = {s_new, out};
        end
    endfunction

    // ------------------------------------------------------------------
    // FSM
    // ------------------------------------------------------------------
    localparam [4:0]
        S_IDLE          = 5'd0,
        S_INIT_LOAD     = 5'd1,
        S_INIT_PERM     = 5'd2,
        S_INIT_XOR      = 5'd3,
        S_AD_CHECK      = 5'd4,
        S_AD_WAIT       = 5'd5,
        S_AD_PERM       = 5'd6,
        S_AD_EXTRA      = 5'd7,
        S_AD_EXTRA_PERM = 5'd8,
        S_AD_DOMSEP     = 5'd9,
        S_PC_WAIT       = 5'd10,
        S_PC_ABSORB     = 5'd11,
        S_PC_OUT_WAIT   = 5'd12,
        S_PC_PERM       = 5'd13,
        S_PC_EXTRA      = 5'd14,
        S_FIN_XOR1      = 5'd15,
        S_FIN_PERM      = 5'd16,
        S_FIN_XOR2      = 5'd17;

    reg [4:0] fsm_state;

    // Per-block scratch: whether the block just absorbed was the last real
    // block on the current stream. Consumed by the state right after the
    // following permute to decide where to go next.
    reg cur_final;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fsm_state        <= S_IDLE;
            state_reg        <= 320'd0;
            busy             <= 1'b0;
            done             <= 1'b0;
            auth_ok          <= 1'b0;
            tag_out          <= 128'd0;
            ad_ready         <= 1'b0;
            pc_ready         <= 1'b0;
            pc_valid_out     <= 1'b0;
            pc_data_out      <= 128'd0;
            pc_bytes_out     <= 5'd0;
            pc_last_out      <= 1'b0;
            perm_a_start     <= 1'b0;
            perm_b_start     <= 1'b0;
            key_reg          <= 128'd0;
            nonce_reg        <= 128'd0;
            tag_in_reg       <= 128'd0;
            decrypt_reg      <= 1'b0;
            ad_remaining     <= 32'd0;
            pc_remaining     <= 32'd0;
            ad_extra_pending <= 1'b0;
            pc_extra_pending <= 1'b0;
            pc_final         <= 1'b0;
            pc_data_reg      <= 128'd0;
            cur_final        <= 1'b0;
        end else begin
            // Default single-cycle pulses/strobes; overridden below where needed.
            done         <= 1'b0;
            perm_a_start <= 1'b0;
            perm_b_start <= 1'b0;
            ad_ready     <= 1'b0;
            pc_ready     <= 1'b0;

            case (fsm_state)

                // ------------------------------------------------------
                S_IDLE: begin
                    if (start) begin
                        key_reg      <= key;
                        nonce_reg    <= nonce;
                        decrypt_reg  <= decrypt;
                        tag_in_reg   <= tag_in;
                        ad_remaining <= ad_len;
                        pc_remaining <= pc_len;
                        busy         <= 1'b1;
                        fsm_state    <= S_INIT_LOAD;
                    end
                end

                // Load S = IV || Key || Nonce and kick off the a=12-round
                // initialization permutation.
                S_INIT_LOAD: begin
                    state_reg    <= {ASCON_IV, key_reg[127:64], key_reg[63:0],
                                      nonce_reg[127:64], nonce_reg[63:0]};
                    perm_a_start <= 1'b1;
                    fsm_state    <= S_INIT_PERM;
                end

                S_INIT_PERM: begin
                    if (perm_a_done) begin
                        state_reg <= perm_a_out;
                        fsm_state <= S_INIT_XOR;
                    end
                end

                // Post-init key XOR (S3,S4), via ascon_keyxor.
                S_INIT_XOR: begin
                    state_reg <= {initxor_x0, initxor_x1, initxor_x2,
                                  initxor_x3, initxor_x4};
                    fsm_state <= S_AD_CHECK;
                end

                // ------------------------------------------------------
                // Associated data. Every block -- including the synthetic
                // all-pad "extra" block used when ad_len is an exact
                // multiple of 16 -- is followed by a b-round permute.
                S_AD_CHECK: begin
                    fsm_state <= (ad_remaining == 32'd0) ? S_AD_DOMSEP : S_AD_WAIT;
                end

                S_AD_WAIT: begin
                    ad_ready <= 1'b1;
                    if (ad_valid) begin
                        begin : ad_absorb
                            reg [127:0] updated;
                            updated = ad_lane_update({s1, s0}, ad_padded_w, ad_valid_bytes_w);
                            state_reg[319:256] <= updated[63:0];
                            state_reg[255:192] <= updated[127:64];
                            cur_final        <= (ad_remaining <= 32'd16);
                            ad_extra_pending <= (ad_remaining <= 32'd16) && (ad_valid_bytes_w == 5'd16);
                            ad_remaining     <= (ad_remaining > 32'd16) ? (ad_remaining - 32'd16) : 32'd0;
                        end
                        perm_b_start <= 1'b1;
                        fsm_state    <= S_AD_PERM;
                    end
                end

                S_AD_PERM: begin
                    if (perm_b_done) begin
                        state_reg <= perm_b_out;
                        if (!cur_final)
                            fsm_state <= S_AD_WAIT;
                        else if (ad_extra_pending)
                            fsm_state <= S_AD_EXTRA;
                        else
                            fsm_state <= S_AD_DOMSEP;
                    end
                end

                // Synthetic empty AD block for the exact-rate-multiple case
                // (still followed by a b-round permute, unlike PT/CT).
                // ad_remaining is guaranteed 0 here (see S_AD_WAIT above),
                // so ad_valid_bytes_w/ad_padded_w already evaluate as the
                // "empty block" case -- no separate zero-literal call.
                S_AD_EXTRA: begin
                    begin : ad_extra_absorb
                        reg [127:0] updated;
                        updated = ad_lane_update({s1, s0}, ad_padded_w, ad_valid_bytes_w);
                        state_reg[319:256] <= updated[63:0];
                        state_reg[255:192] <= updated[127:64];
                    end
                    perm_b_start <= 1'b1;
                    fsm_state    <= S_AD_EXTRA_PERM;
                end

                S_AD_EXTRA_PERM: begin
                    if (perm_b_done) begin
                        state_reg <= perm_b_out;
                        fsm_state <= S_AD_DOMSEP;
                    end
                end

                // Domain-separation bit: S4 ^= 1<<63.
                S_AD_DOMSEP: begin
                    state_reg[63] <= ~state_reg[63];
                    fsm_state     <= S_PC_WAIT;
                end

                // ------------------------------------------------------
                // Plaintext (encrypt) / ciphertext (decrypt) processing.
                // Unlike AD, only non-final blocks are followed by a
                // permute; the final block (real or synthetic-empty) is
                // followed straight by finalization.
                S_PC_WAIT: begin
                    if (pc_remaining == 32'd0) begin
                        // Empty PT/CT: synthesize the lone pad-only block
                        // without waiting for an external beat.
                        pc_data_reg <= 128'd0;
                        fsm_state   <= S_PC_ABSORB;
                    end else begin
                        pc_ready <= 1'b1;
                        if (pc_valid) begin
                            pc_data_reg <= pc_data_in;
                            fsm_state   <= S_PC_ABSORB;
                        end
                    end
                end

                S_PC_ABSORB: begin
                    begin : pc_absorb
                        reg [255:0] result;
                        result = pc_lane_update({s1, s0}, pc_padded_w, pc_valid_bytes_w, decrypt_reg);
                        state_reg[319:256] <= result[255:192];
                        state_reg[255:192] <= result[191:128];
                        cur_final        <= (pc_remaining <= 32'd16);
                        pc_final         <= (pc_remaining <= 32'd16);
                        pc_extra_pending <= (pc_remaining <= 32'd16) && (pc_valid_bytes_w == 5'd16);
                        pc_remaining     <= (pc_remaining > 32'd16) ? (pc_remaining - 32'd16) : 32'd0;
                        if (pc_valid_bytes_w != 5'd0) begin
                            pc_data_out  <= result[127:0];
                            pc_bytes_out <= pc_valid_bytes_w;
                            pc_last_out  <= (pc_remaining <= 32'd16);
                            pc_valid_out <= 1'b1;
                            fsm_state    <= S_PC_OUT_WAIT;
                        end else begin
                            // Empty PT/CT: no output beat to emit.
                            fsm_state <= S_FIN_XOR1;
                        end
                    end
                end

                S_PC_OUT_WAIT: begin
                    if (pc_ready_in) begin
                        pc_valid_out <= 1'b0;
                        if (!pc_final || pc_extra_pending) begin
                            perm_b_start <= 1'b1;
                            fsm_state    <= S_PC_PERM;
                        end else begin
                            fsm_state <= S_FIN_XOR1;
                        end
                    end
                end

                S_PC_PERM: begin
                    if (perm_b_done) begin
                        state_reg <= perm_b_out;
                        if (!pc_final)
                            fsm_state <= S_PC_WAIT;
                        else if (pc_extra_pending)
                            fsm_state <= S_PC_EXTRA;
                        else
                            fsm_state <= S_FIN_XOR1;
                    end
                end

                // Synthetic empty PT/CT block for the exact-rate-multiple
                // case. No permute follows (finalization's permute takes
                // its place), and it produces no output bytes.
                // pc_remaining is guaranteed 0 here (see S_PC_ABSORB
                // above), so pc_valid_bytes_w/pc_padded_w already evaluate
                // as the "empty block" case -- no separate zero-literal
                // call.
                S_PC_EXTRA: begin
                    begin : pc_extra_absorb
                        reg [255:0] result;
                        result = pc_lane_update({s1, s0}, pc_padded_w, pc_valid_bytes_w, decrypt_reg);
                        state_reg[319:256] <= result[255:192];
                        state_reg[255:192] <= result[191:128];
                    end
                    fsm_state <= S_FIN_XOR1;
                end

                // ------------------------------------------------------
                // Finalization: S2^=key0, S3^=key1, permute(a=12),
                // S3^=key0, S4^=key1, tag = S3||S4.
                S_FIN_XOR1: begin
                    state_reg[191:128] <= s2 ^ key_w0;
                    state_reg[127:64]  <= s3 ^ key_w1;
                    perm_a_start       <= 1'b1;
                    fsm_state          <= S_FIN_PERM;
                end

                S_FIN_PERM: begin
                    if (perm_a_done) begin
                        state_reg <= perm_a_out;
                        fsm_state <= S_FIN_XOR2;
                    end
                end

                S_FIN_XOR2: begin
                    begin : finalize
                        reg [63:0] tag_s3, tag_s4;
                        tag_s3 = s3 ^ key_w0;
                        tag_s4 = s4 ^ key_w1;
                        state_reg[127:64] <= tag_s3;
                        state_reg[63:0]   <= tag_s4;
                        tag_out <= {tag_s3, tag_s4};
                        auth_ok <= decrypt_reg ? ({tag_s3, tag_s4} == tag_in_reg) : 1'b1;
                    end
                    busy      <= 1'b0;
                    done      <= 1'b1;
                    fsm_state <= S_IDLE;
                end

                default: fsm_state <= S_IDLE;
            endcase
        end
    end

endmodule
