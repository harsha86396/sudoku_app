
from app import app

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=5000, debug=bool(int(os.environ.get("DEBUG", "0"))))
