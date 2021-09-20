from flask import Flask, make_response, render_template

from cvd import healthcheck

app = Flask(__name__)


@app.route("/")
def p1_check():

    status, text = healthcheck()

    content = render_template("pingdom-check.xml", status=status, text=text)
    response = make_response(content)
    response.headers["Content-Type"] = "application/xml"

    return response
