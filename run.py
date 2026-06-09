
from inventory import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="192.168.0.54", port=5090, debug=True)
