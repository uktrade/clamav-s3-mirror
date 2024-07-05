from flask import Flask, make_response, render_template

from cvd import healthcheck

app = Flask(__name__)


@app.route("/")
def index():
    return "OK"


@app.route("/healthcheck")
def p1_check():
    """
    p1 pingdom xml healthcheck endpoint view.

    If the main database or diff is greater than 1 version out of date, then this endpoint
    will report a FAIL, which will lead to a pingdom alert.
    """

    status, text = healthcheck()

    content = render_template("pingdom-check.xml", status=status, text=text)
    response = make_response(content)
    response.headers["Content-Type"] = "application/xml"

    return response
