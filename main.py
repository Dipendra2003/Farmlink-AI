from app import app
import logging
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

if __name__ == '__main__':
    try:
        print("=" * 50)
        print("Starting FarmLink AI Server...")
        print("=" * 50)
        print(f"Server will be available at: http://127.0.0.1:5000")
        print("=" * 50)
        # Get debug mode from environment (default False for production safety)
        debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
        app.run(host='0.0.0.0', port=5000, debug=debug_mode, use_reloader=debug_mode, threaded=True)
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Server failed to start!")
        print(f"{'='*50}")
        print(f"Error details: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

