from waitress import serve
from app import app
import logging

# Set up simple logging to see access logs in the terminal
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('waitress')

if __name__ == '__main__':
    print("-" * 50)
    print("GCE SALEM SCRUTINY DASHBOARD - PRODUCTION MODE")
    print("Server is running on: http://localhost:5000")
    print("Press Ctrl+C to stop the server.")
    print("-" * 50)
    
    # host='0.0.0.0' allows other computers on your Wi-Fi to access the dashboard
    # threads=8 allows 8 people to work on the dashboard at the same time
    serve(app, host='0.0.0.0', port=5000, threads=8)