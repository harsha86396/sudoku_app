from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_mail import Mail, Message
import os, random, string

app = Flask(__name__)
app.secret_key = "supersecret"

# Email setup (uses environment or defaults)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("SMTP_USER", "harsha86396@gmail.com")
app.config['MAIL_PASSWORD'] = os.getenv("SMTP_PASS", "mstxbkcvhtstpncp")
mail = Mail(app)

users = {}  # mock in-memory db
reset_codes = {}

@app.route("/")
def index():
    if "user" in session:
        return render_template("game.html", user=session["user"])
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    email = request.form["email"]
    password = request.form["password"]
    if email in users:
        return "User already exists!"
    users[email] = {"password": password}
    return redirect(url_for("index"))

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]
    if email in users and users[email]["password"] == password:
        session["user"] = email
        return redirect(url_for("index"))
    return "Invalid login"

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("index"))

@app.route("/forgot", methods=["POST"])
def forgot():
    email = request.form["email"]
    if email not in users:
        return "No account with this email"
    code = "".join(random.choices(string.digits, k=6))
    reset_codes[email] = code
    msg = Message("Your Password Reset Code", recipients=[email], body=f"Code: {code}")
    mail.send(msg)
    return "Reset code sent to your email"

@app.route("/reset", methods=["POST"])
def reset():
    email = request.form["email"]
    code = request.form["code"]
    newpass = request.form["password"]
    if reset_codes.get(email) == code:
        users[email]["password"] = newpass
        reset_codes.pop(email, None)
        return "Password reset successful!"
    return "Invalid reset code"
    
@app.route("/api/record_result", methods=["POST"])
def record_result():
    if "user" not in session:
        return jsonify({"error": "not logged in"}), 401
    data = request.get_json()
    return jsonify({"message": f"Result recorded for {session['user']}", "data": data})

if __name__ == "__main__":
    app.run(debug=True)
