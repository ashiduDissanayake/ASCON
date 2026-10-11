"""Tkinter view/controller. Packet and serial logic live in separate modules."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font
from .protocol import (DEFAULT_KEY, DEFAULT_AD, DEFAULT_PLAINTEXT, DEFAULT_NONCE,
                       DEFAULT_CT, DEFAULT_TAG, make_request, new_nonce)
from .transport import SerialTransport, DemoTransport, list_ports
from .service import run_operation, save_result


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        families = {name.lower() for name in font.families(self)}
        self.ui_font = 'Segoe UI' if 'segoe ui' in families else 'Helvetica'
        self.code_font = 'Consolas' if 'consolas' in families else 'Courier'
        self.title('ASCON | Streaming UART v3')
        width = min(1120, max(400, self.winfo_screenwidth() - 100))
        height = min(760, max(350, self.winfo_screenheight() - 150))
        self.geometry(f'{width}x{height}')
        self.minsize(min(640, width), min(480, height))
        self.configure(bg='#f3f5f7')
        self.transport = None
        self.source = ''
        self.result = None
        self.pending = False
        self.events = queue.Queue()
        self.controls = []
        self.operation = tk.StringVar(value='Encrypt')
        self.backend = tk.StringVar(value='FPGA hardware')
        self.port = tk.StringVar()
        self.encoding = tk.StringVar(value='UTF-8 text')
        self.key = tk.StringVar()
        self.nonce = tk.StringVar()
        self.ad = tk.StringVar()
        self.data = tk.StringVar()
        self.tag = tk.StringVar()
        self.auto_nonce = tk.BooleanVar(value=True)
        self.empty_ad = tk.BooleanVar(value=False)
        self.empty_data = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Disconnected - program the FPGA and press btnC before connecting.')
        self.output_status = tk.StringVar(value='No response yet')
        self.round_trip = tk.StringVar(value='Round trip: —')
        self.auth_status = tk.StringVar(value='No result yet')
        self._wheel_remainder = 0.0
        self._build()
        self._defaults()
        self.refresh_ports()
        self.after(60, self._poll)
        self.protocol('WM_DELETE_WINDOW', self._close)

    def _track_widget(self, widget, normal='normal'):
        self.controls.append((widget, normal))
        return widget

    def _build(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=(self.ui_font, 10))
        style.configure('TFrame', background='#f3f5f7')
        style.configure('TLabel', background='#f3f5f7', foreground='#233043')
        style.configure('Title.TLabel', font=(self.ui_font, 21, 'bold'))
        style.configure('TLabelframe', background='#f3f5f7')
        style.configure('TLabelframe.Label', font=(self.ui_font, 11, 'bold'), background='#f3f5f7')
        style.configure('TButton', padding=(12, 7))
        for name, fg, bg in [('Neutral', '#475569', '#e2e8f0'), ('Success', '#166534', '#dcfce7'), ('Failure', '#991b1b', '#fee2e2'), ('Pending', '#92400e', '#fef3c7')]:
            style.configure(name + '.TLabel', foreground=fg, background=bg, padding=(8, 5), font=(self.ui_font, 10, 'bold'))
        style.configure('Accent.TButton', foreground='white', background='#255c82')
        # The form normally fits without chrome. Reveal an outer scrollbar only
        # when a smaller window makes the responsive layout taller than its view.
        shell = ttk.Frame(self)
        shell.pack(fill='both', expand=True)
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(shell, background='#f3f5f7', highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.page_scroll = ttk.Scrollbar(shell, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.page_scroll.set)
        main = self.main_frame = ttk.Frame(self.canvas, padding=16)
        self.content_id = self.canvas.create_window(0, 0, window=main, anchor='nw')
        main.bind('<Configure>', self._content_resized)
        self.canvas.bind('<Configure>', self._layout_viewport)
        self.bind_class('AsconWheel', '<MouseWheel>', self._wheel)
        self.bind_class('AsconWheel', '<Button-4>', self._wheel)
        self.bind_class('AsconWheel', '<Button-5>', self._wheel)
        self._narrow = None
        ttk.Label(main, text='ASCON FPGA Console', style='Title.TLabel').pack(anchor='w')
        conn = self.connection_frame = ttk.LabelFrame(main, text='Connection', padding=8)
        conn.pack(fill='x')
        self.backend_combo = self._track_widget(ttk.Combobox(conn, textvariable=self.backend, values=['FPGA hardware', 'Software demo'], width=19, state='readonly'), 'readonly')
        self.backend_combo.grid(row=0, column=0, padx=(0, 10))
        self.port_combo = self._track_widget(ttk.Combobox(conn, textvariable=self.port, width=18, state='readonly'), 'readonly')
        self.port_combo.grid(row=0, column=1, padx=(0, 10))
        self._track_widget(ttk.Button(conn, text='Refresh ports', command=self.refresh_ports)).grid(row=0, column=2, padx=(0, 10))
        self.connect_button = self._track_widget(ttk.Button(conn, text='Connect', command=self._connect))
        self.connect_button.grid(row=0, column=3)
        ttk.Label(conn, text='115200 | UART v3').grid(row=0, column=4, padx=16)
        self.connection_status = ttk.Label(conn, textvariable=self.status, wraplength=950)
        self.connection_status.grid(row=1, column=0, columnspan=5, sticky='w', pady=(9, 0))
        self.connection_controls = [w for w in conn.winfo_children() if w is not self.connection_status]
        columns = self.panel_frame = ttk.Frame(main)
        columns.pack(fill='both', expand=True, pady=16)
        columns.columnconfigure(0, weight=1, uniform='panels')
        columns.columnconfigure(1, weight=1, uniform='panels')
        left = self.left_panel = ttk.LabelFrame(columns, text='Send to FPGA', padding=14)
        right = self.right_panel = ttk.LabelFrame(columns, text='Received result', padding=14)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        right.grid(row=0, column=1, sticky='nsew', padx=(8, 0))
        left.columnconfigure(0, weight=1)
        op = self._track_widget(ttk.Combobox(left, textvariable=self.operation, values=['Encrypt', 'Decrypt + verify'], state='readonly'), 'readonly')
        op.grid(row=0, column=0, sticky='ew')
        op.bind('<<ComboboxSelected>>', lambda _: self._defaults())
        ttk.Label(left, text='Changing operation loads example inputs.', font=(self.ui_font, 9)).grid(row=1, column=0, sticky='w', pady=(3, 6))
        row = 2
        for label, variable in [('Key | 16 bytes, hex', self.key), ('Nonce | 16 bytes, hex', self.nonce)]:
            ttk.Label(left, text=label).grid(row=row, column=0, sticky='w', pady=(7, 3))
            self._track_widget(ttk.Entry(left, textvariable=variable, font=(self.code_font, 10))).grid(row=row+1, column=0, sticky='ew')
            row += 2
        self.nonce_check = self._track_widget(ttk.Checkbutton(left, text='Fresh random nonce for each encryption', variable=self.auto_nonce))
        self.nonce_check.grid(row=6, column=0, sticky='w', pady=(5, 0))
        options = ttk.Frame(left)
        options.grid(row=7, column=0, sticky='ew', pady=(9, 0))
        ttk.Label(options, text='Input encoding').pack(side='left')
        self.encoding_combo = self._track_widget(ttk.Combobox(options, textvariable=self.encoding, values=['UTF-8 text', 'Hex bytes'], width=13, state='readonly'), 'readonly')
        self.encoding_combo.pack(side='right')
        self.encoding_combo.bind('<<ComboboxSelected>>', self._encoding_changed)
        ttk.Label(left, text='Associated data | streamed in 16-byte blocks').grid(row=8, column=0, sticky='w', pady=(8, 3))
        self._track_widget(ttk.Entry(left, textvariable=self.ad)).grid(row=9, column=0, sticky='ew')
        self._track_widget(ttk.Checkbutton(left, text='Use empty AD', variable=self.empty_ad)).grid(row=10, column=0, sticky='w')
        self.data_label = ttk.Label(left)
        self.data_label.grid(row=11, column=0, sticky='w', pady=(7, 3))
        self._track_widget(ttk.Entry(left, textvariable=self.data)).grid(row=12, column=0, sticky='ew')
        self._track_widget(ttk.Checkbutton(left, text='Use empty input data', variable=self.empty_data)).grid(row=13, column=0, sticky='w')
        ttk.Label(left, text='Authentication tag | decryption only, hex').grid(row=14, column=0, sticky='w', pady=(7, 3))
        self.tag_entry = self._track_widget(ttk.Entry(left, textvariable=self.tag, font=(self.code_font, 10)))
        self.tag_entry.grid(row=15, column=0, sticky='ew')
        file_actions = ttk.Frame(left)
        file_actions.grid(row=16, column=0, sticky='ew', pady=(10, 0))
        self._track_widget(ttk.Button(file_actions, text='Load AD file', command=lambda: self._load_file(True))).pack(side='left')
        self._track_widget(ttk.Button(file_actions, text='Load data file', command=lambda: self._load_file(False))).pack(side='right')
        actions = ttk.Frame(left)
        actions.grid(row=17, column=0, sticky='ew', pady=(12, 0))
        self.send_button = ttk.Button(actions, text='Send & encrypt', style='Accent.TButton', command=self._send, state='disabled')
        self.send_button.pack(side='left')
        self._track_widget(ttk.Button(actions, text='Load defaults', command=self._defaults)).pack(side='right')
        ttk.Label(left, text='Blank fields use defaults. Tick "Use empty" for zero bytes.\nThe example key is for lab testing.', font=(self.ui_font, 9)).grid(row=18, column=0, sticky='w', pady=(9, 0))
        result_header = ttk.Frame(right)
        result_header.pack(fill='x', pady=(0, 10))
        self.auth_badge = ttk.Label(result_header, textvariable=self.auth_status, style='Neutral.TLabel')
        self.auth_badge.pack(side='left')
        self.time_label = ttk.Label(result_header, textvariable=self.round_trip, font=(self.ui_font, 10, 'bold'))
        self.time_label.pack(side='right', padx=(10, 0))
        self.source_label = ttk.Label(right, textvariable=self.output_status, wraplength=420)
        self.source_label.pack(anchor='w', pady=(0, 10))
        output_frame = ttk.Frame(right)
        output_frame.pack(fill='both', expand=True)
        self.output = tk.Text(output_frame, width=32, height=16, wrap='word', font=(self.code_font, 10), relief='flat', padx=12, pady=12, bg='white', fg='#233043', state='disabled')
        self.output.pack(side='left', fill='both', expand=True)
        output_scroll = ttk.Scrollbar(output_frame, orient='vertical', command=self.output.yview)
        output_scroll.pack(side='right', fill='y')
        self.output.configure(yscrollcommand=output_scroll.set)
        self.output_scroll = output_scroll
        export = ttk.Frame(right)
        export.pack(fill='x', pady=(12, 0))
        self.save_button = ttk.Button(export, text='Export result JSON', command=self._export, state='disabled')
        self.save_button.pack(side='left')
        self.copy_button = ttk.Button(export, text='Copy output hex', command=self._copy, state='disabled')
        self.copy_button.pack(side='right')
        self.decrypt_result_button = ttk.Button(right, text='Load this result for decryption', command=self._load_decrypt, state='disabled')
        self.decrypt_result_button.pack(anchor='w', pady=(9, 0))
        ttk.Label(right, text='Export contains ciphertext, nonce, AD and tag.\nThe key and plaintext are not exported.', font=(self.ui_font, 9)).pack(anchor='w', pady=(10, 0))
        self._install_scroll_bindings(self.main_frame)
        self.after_idle(lambda: self._layout_viewport())

    def _layout_viewport(self, event=None):
        if not hasattr(self, 'right_panel'):
            return
        width = max(1, self.canvas.winfo_width())
        # Actual font/widget measurements include the current OS DPI scaling.
        threshold = self.left_panel.winfo_reqwidth() + self.right_panel.winfo_reqwidth() + 70
        narrow = width < threshold
        if narrow != self._narrow:
            self._narrow = narrow
            self.panel_frame.columnconfigure(1, weight=0 if narrow else 1, uniform='' if narrow else 'panels')
            self.panel_frame.columnconfigure(0, weight=1, uniform='' if narrow else 'panels')
            self.left_panel.grid_configure(row=0, column=0, padx=(0, 0 if narrow else 8))
            self.right_panel.grid_configure(row=1 if narrow else 0, column=0 if narrow else 1,
                                            padx=(0 if narrow else 8, 0), pady=(12 if narrow else 0, 0))
            for index, widget in enumerate(self.connection_controls):
                widget.grid_configure(row=index // 2 if narrow else 0,
                                      column=index % 2 if narrow else index, sticky='w', padx=(0, 10), pady=3)
            self.connection_status.grid_configure(row=3 if narrow else 1, columnspan=2 if narrow else 5)
        self.connection_status.configure(wraplength=max(240, width - 80))
        for child in self.main_frame.winfo_children():
            if isinstance(child, ttk.Label):
                child.configure(wraplength=max(240, width - 50))
        self.update_idletasks()
        self.canvas.itemconfigure(self.content_id, width=width)
        self.source_label.configure(wraplength=max(240, self.right_panel.winfo_width()-40))
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self._update_page_scrollbar()

    def _content_resized(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self.after_idle(self._update_page_scrollbar)

    def _update_page_scrollbar(self):
        if not self.winfo_exists():
            return
        content_height = self.main_frame.winfo_reqheight()
        viewport_height = self.canvas.winfo_height()
        needs_scroll = content_height > viewport_height + 1
        if needs_scroll and not self.page_scroll.winfo_ismapped():
            self.page_scroll.grid(row=0, column=1, sticky='ns')
        elif not needs_scroll and self.page_scroll.winfo_ismapped():
            self.canvas.yview_moveto(0)
            self.page_scroll.grid_remove()

    def _install_scroll_bindings(self, widget):
        # Run before widget/class defaults: one wheel event scrolls exactly once.
        widget.bindtags(('AsconWheel',) + widget.bindtags())
        for child in widget.winfo_children():
            self._install_scroll_bindings(child)

    def _wheel(self, event):
        if event.widget.winfo_toplevel() is not self:
            return
        num, delta = getattr(event, 'num', 0), getattr(event, 'delta', 0)
        if num in (4, 5):
            units = -3 if num == 4 else 3
        else:
            scale = 1 if self.tk.call('tk', 'windowingsystem') == 'aqua' else 120
            self._wheel_remainder += -delta / scale * 3
            units = int(self._wheel_remainder)
            self._wheel_remainder -= units
            if not units:
                return 'break'
        # Prefer the result pane's own scroll; otherwise scroll the page only
        # when the reduced window has caused the outer scrollbar to appear.
        if event.widget in (self.output, self.output_scroll):
            first, last = self.output.yview()
            if (units < 0 and first > 0.00001) or (units > 0 and last < 0.99999):
                self.output.yview_scroll(units, 'units')
        elif self.page_scroll.winfo_ismapped():
            first, last = self.canvas.yview()
            if (units < 0 and first > 0.00001) or (units > 0 and last < 0.99999):
                self.canvas.yview_scroll(units, 'units')
        return 'break'

    def _set_result_status(self, text, tone='Neutral'):
        self.auth_status.set(text)
        self.auth_badge.configure(style=tone + '.TLabel')

    def _load_file(self, associated):
        path = filedialog.askopenfilename(title='Load associated data' if associated else 'Load plaintext / ciphertext bytes')
        if not path:
            return
        try:
            with open(path, 'rb') as source:
                data = source.read()
            if self.encoding.get() != 'Hex bytes':
                self.encoding.set('Hex bytes')
                self._encoding_changed()
            (self.ad if associated else self.data).set(data.hex())
            (self.empty_ad if associated else self.empty_data).set(not data)
            self.status.set(f'Loaded {len(data)} bytes. Files are represented as hex in the input field.')
        except (OSError, ValueError) as exc:
            messagebox.showerror('File input', str(exc))

    def refresh_ports(self):
        ports = list_ports()
        self.port_combo['values'] = [port for port, _ in ports]
        if ports and self.port.get() not in [p for p, _ in ports]:
            self.port.set(ports[0][0])

    def _defaults(self):
        decrypt = self.operation.get() != 'Encrypt'
        self.encoding.set('UTF-8 text')
        self.key.set(DEFAULT_KEY)
        self.nonce.set(DEFAULT_NONCE if decrypt else new_nonce())
        self.ad.set(DEFAULT_AD)
        self.data.set(DEFAULT_CT if decrypt else DEFAULT_PLAINTEXT)
        self.tag.set(DEFAULT_TAG if decrypt else '')
        self.auto_nonce.set(not decrypt)
        self.empty_ad.set(False)
        self.empty_data.set(False)
        self.data_label.configure(text='Ciphertext | hex, streamed in 16-byte blocks' if decrypt else 'Plaintext | streamed in 16-byte blocks')
        self.send_button.configure(text='Send & decrypt' if decrypt else 'Send & encrypt')
        self._states()

    def _encoding_changed(self, _=None):
        # Preserve the bytes when switching display encodings.
        to_hex = self.encoding.get() == 'Hex bytes'
        variables = [self.ad] + ([self.data] if self.operation.get() == 'Encrypt' else [])
        try:
            converted = [v.get().encode('utf-8').hex() if to_hex else bytes.fromhex(v.get()).decode('utf-8') for v in variables]
            for var, value in zip(variables, converted):
                var.set(value)
        except (ValueError, UnicodeDecodeError):
            self.encoding.set('UTF-8 text' if to_hex else 'Hex bytes')
            messagebox.showerror('Encoding', 'These values cannot be converted. Keep hex mode for arbitrary bytes.')

    def _states(self):
        for widget, normal in self.controls:
            widget.configure(state='disabled' if self.pending else normal)
        if not self.pending:
            if self.transport:
                self.backend_combo.configure(state='disabled')
                self.port_combo.configure(state='disabled')
            self.tag_entry.configure(state='normal' if self.operation.get() != 'Encrypt' else 'disabled')
            self.nonce_check.configure(state='normal' if self.operation.get() == 'Encrypt' else 'disabled')
        self.send_button.configure(state='normal' if self.transport and not self.pending else 'disabled')
        for button in (self.save_button, self.copy_button):
            button.configure(state='normal' if self.result and not self.pending else 'disabled')
        self.decrypt_result_button.configure(state='normal' if self.result and self.result['operation'] == 'encrypt' and not self.pending else 'disabled')
        self.connect_button.configure(text='Disconnect' if self.transport else 'Connect')

    def _work(self, kind, function):
        self.pending = True
        self._states()
        def worker():
            try:
                self.events.put((kind, function(), None))
            except Exception as exc:
                self.events.put((kind, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _connect(self):
        if self.transport:
            self._work('disconnect', self.transport.close)
        else:
            demo = self.backend.get() == 'Software demo'
            port = self.port.get()
            if not demo and not port:
                messagebox.showerror('Select a port', 'Connect Basys3 and click Refresh ports, then select its COM port.')
                return
            self.source = 'SOFTWARE DEMO - no FPGA used' if demo else f'FPGA hardware on {port}'
            self.status.set('Connecting...')
            self._work('connect', lambda: DemoTransport() if demo else SerialTransport(port))

    def _send(self):
        decrypt = self.operation.get() != 'Encrypt'
        try:
            nonce = new_nonce() if self.auto_nonce.get() and not decrypt else self.nonce.get()
            request = make_request(self.key.get(), nonce, self.ad.get(), self.data.get(),
                                   self.encoding.get(), self.empty_ad.get(), self.empty_data.get(), decrypt, self.tag.get())
        except ValueError as exc:
            messagebox.showerror('Check inputs', str(exc))
            return
        self.key.set(request.key.hex())
        self.nonce.set(request.nonce.hex())
        self.ad.set(request.ad.hex() if self.encoding.get() == 'Hex bytes' else request.ad.decode('utf-8'))
        self.data.set(request.plaintext.hex() if decrypt or self.encoding.get() == 'Hex bytes' else request.plaintext.decode('utf-8'))
        if decrypt:
            self.tag.set(request.tag.hex())
        self.last_request = request
        self.result = None
        self.round_trip.set('Round trip: —')
        self._set_result_status('Verifying…' if decrypt else 'Encrypting…', 'Pending')
        self._show('Waiting for response...')
        self.output_status.set(f'{self.source} | processing')
        self.status.set('Streaming input/output blocks; waiting for final authentication tag...')
        transport, source = self.transport, self.source
        def transact():
            try:
                return run_operation(transport, request, source)
            except Exception:
                transport.close()
                raise
        self._work('transaction', transact)

    def _poll(self):
        try:
            kind, value, error = self.events.get_nowait()
        except queue.Empty:
            self.after(60, self._poll)
            return
        self.pending = False
        if error:
            if kind in ('transaction', 'disconnect'):
                self.transport = None
            self.result = None
            self.status.set(error)
            self.round_trip.set('Round trip: —')
            self._set_result_status('Authentication failed' if 'Authentication failed' in error else 'Operation failed', 'Failure')
            self.output_status.set('No successful result')
            self._show(error)
        elif kind == 'connect':
            self.transport = value
            self.status.set(f'Connected: {self.source}')
        elif kind == 'disconnect':
            self.transport = None
            self.status.set('Disconnected')
        else:
            self.result = value
            decrypt = value['operation'] == 'decrypt'
            self.output_status.set(value['source'])
            self._set_result_status('Authentication verified' if decrypt else 'Encryption complete', 'Success')
            self.round_trip.set(f"Round trip: {value['round_trip_ms']:,.3f} ms")
            data = value['plaintext_hex'] if decrypt else value['ciphertext_hex']
            text = f"{'PLAINTEXT' if decrypt else 'CIPHERTEXT'} (hex)\n{data or '(empty)'}\n\n"
            if decrypt:
                try:
                    text += 'PLAINTEXT (UTF-8)\n' + bytes.fromhex(data).decode('utf-8') + '\n\n'
                except UnicodeDecodeError:
                    text += 'Plaintext is binary; view the hex above.\n\n'
            text += f"TAG (hex)\n{value['tag_hex']}\n\nNONCE USED\n{value['nonce_hex']}\n\nAD (hex)\n{value['associated_data_hex']}\n\nINPUT: {value['plaintext_bytes']} bytes"
            self._show(text)
            self.status.set('Complete - ready for another request.')
        self._states()
        self.after(60, self._poll)

    def _show(self, text):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', text)
        self.output.configure(state='disabled')
        self.output.yview_moveto(0)

    def _load_decrypt(self):
        result, request = self.result, self.last_request
        self.operation.set('Decrypt + verify')
        self._defaults()
        self.encoding.set('Hex bytes')
        self.key.set(request.key.hex())
        self.nonce.set(result['nonce_hex'])
        self.ad.set(result['associated_data_hex'])
        self.data.set(result['ciphertext_hex'])
        self.tag.set(result['tag_hex'])
        self.empty_ad.set(not request.ad)
        self.empty_data.set(not request.plaintext)
        self.status.set('Previous encryption loaded. Send to verify and recover the plaintext.')

    def _export(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='ascon_result.json', filetypes=[('JSON result', '*.json')])
        if path:
            try:
                save_result(path, self.result)
                self.status.set('Result exported. Share the key separately if the recipient needs decryption.')
            except OSError as exc:
                messagebox.showerror('Export failed', str(exc))

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.result['plaintext_hex'] if self.result['operation'] == 'decrypt' else self.result['ciphertext_hex'])

    def _close(self):
        if self.pending:
            self.status.set('Wait for the current operation to finish before closing (timeout is 3 seconds of serial inactivity).')
            return
        if self.transport:
            self.transport.close()
        self.destroy()
