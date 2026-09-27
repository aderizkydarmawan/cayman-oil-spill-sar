import http.server
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy","same-origin"); self.send_header("Cross-Origin-Embedder-Policy","require-corp"); super().end_headers()
http.server.ThreadingHTTPServer(("127.0.0.1",8765),H).serve_forever()
