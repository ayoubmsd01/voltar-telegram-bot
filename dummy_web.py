import http.server
import socketserver
import os

PORT = int(os.environ.get("PORT", 8080))

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
        
    def log_message(self, format, *args):
        # Silence HTTP logs
        pass

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
        print(f"Dummy healthcheck server starting at port {PORT}")
        httpd.serve_forever()
