import os
from server import app

if __name__ == "__main__":
    # Get host and port from environment or use defaults
    host = os.getenv("HOST", "localhost")
    port = int(os.getenv("PORT", 8000))
    
    # Run with production settings
    app.run(
        host=host,
        port=port,
        debug=False,
        access_log=True,
        # One worker by default: each worker has its own cache, sessions and request throttle,
        # so more workers means more traffic to TrackWrestling and a higher chance of a block.
        workers=int(os.getenv("WORKERS", 1)),
    )
