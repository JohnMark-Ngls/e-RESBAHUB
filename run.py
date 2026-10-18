"""Start the e-RESBAHUB development server:  python run.py"""
from resbahub import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True auto-reloads on code changes. Turn it OFF for real deployment.
    app.run(host="127.0.0.1", port=5000, debug=True)
