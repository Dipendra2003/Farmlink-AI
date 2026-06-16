from app import app
import sys
import os

if __name__ == '__main__':
    try:
        # Get port from environment (Render provides PORT variable)
        port = int(os.environ.get('PORT', 5000))
        
        # Only print startup message in main process (not reloader)
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            print("\n" + "=" * 50)
            print("FarmLink AI Server Starting...")
            print("=" * 50)
        
        # Get debug mode from environment (default False for production safety)
        debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
        
        # Set reloader to only watch specific directories (not site-packages)
        # This prevents the infinite reload loop from PyTorch files
        extra_files = []
        
        app.run(
            host='0.0.0.0', 
            port=port, 
            debug=debug_mode, 
            use_reloader=debug_mode,
            threaded=True
        )
    except Exception as e:
        print(f"\n{'='*50}")
        print(f"ERROR: Server failed to start!")
        print(f"{'='*50}")
        print(f"Error details: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

