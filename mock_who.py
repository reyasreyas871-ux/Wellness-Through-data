from flask import Flask, request, jsonify

app = Flask(__name__)

@app.post("/receive")
def receive():
    payload = request.get_json(silent=True) or {}
    # In real life: verify signatures, schema validation, store securely.
    return jsonify({"received": True, "keys": list(payload.keys())})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)