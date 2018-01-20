#!/usr/bin/env python
# -*- coding: utf-8 -*-

################################################
#       Supporting Information Generator       #
# -------------------------------------------- #
# By Jaime RGP <jaime@insilichem.com> @ 2016   #
################################################

from __future__ import unicode_literals, print_function, division, absolute_import
import os
import json
from uuid import uuid4
import datetime
import shutil
from textwrap import dedent
from flask import Flask, request, redirect, url_for, render_template, send_from_directory
from werkzeug.utils import secure_filename
from flask_sslify import SSLify
from esigen import ESIgenReport

app = Flask(__name__)

PRODUCTION = False
if os.environ.get('IN_PRODUCTION'):
    # only trigger SSLify if the app is running on Heroku
    PRODUCTION = True
    sslify = SSLify(app)

UPLOADS = "/tmp"

app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.jinja_env.globals['MAX_CONTENT_LENGTH'] = 50
app.config['PRODUCTION'] = PRODUCTION
app.config['UPLOADS'] = UPLOADS
app.jinja_env.globals['IN_PRODUCTION'] = PRODUCTION
app.jinja_env.globals['HEROKU_RELEASE_VERSION'] = os.environ.get('HEROKU_RELEASE_VERSION', '')
ALLOWED_EXTENSIONS = ('.qfi', '.out', '.log')
URL_KWARGS = dict(_external=True, _scheme='https') if PRODUCTION else {}


@app.route("/")
def index():
    message = str(request.args.get('message', ''))[:100]
    uuid = str(uuid4())
    while os.path.exists(os.path.join(UPLOADS, uuid)):
        uuid = str(uuid4())
    return render_template("index.html", uuid=uuid, message=message)


@app.route("/upload", methods=["POST"])
def upload():
    """Handle the upload of a file."""
    form = request.form
    upload_key = form['upload_key']
    # Is the upload using Ajax, or a direct POST by the form?
    is_ajax = False
    if form.get("__ajax", None) == "true":
        is_ajax = True

    # Target folder for these uploads.
    target = os.path.join(UPLOADS, upload_key)
    try:
        os.makedirs(target)
    except Exception as e:
        if not isinstance(e, OSError):
            return redirect(url_for("index", message="Upload error. Try again", **URL_KWARGS))

    for upload in allowed_filename(*request.files.getlist("file")):
        filename = secure_filename(upload.filename).rsplit("/")[0]
        destination = os.path.join(target, filename)
        upload.save(destination)

    if is_ajax:
        return ajax_response(True, upload_key)
    else:
        return redirect(url_for("configure_report", **URL_KWARGS))


@app.route("/configure", methods=["GET", "POST"])
def configure_report():
    if request.method == 'POST':
        form = request.form
        upload_key = form['upload_key']
        templates = ['default', 'simple']
        styles = ['github']
        return render_template("config.html", templates=templates,
                               styles=styles, uuid=upload_key)
    return redirect(url_for("index", **URL_KWARGS))


@app.route("/report/<uuid>", methods=["GET", "POST"])
def report(uuid, template='default', css='github', show_NAs=True,
           reporter=ESIgenReport):
    """The location we send them to at the end of the upload."""
    if not uuid:
        return redirect(url_for("index", **URL_KWARGS))
    custom_template = False
    if request.method == 'POST':
        form = request.form
        template = form['template']
        css = form['css']
        if template == 'custom':
            custom_template = True
            template = form['template-custom']
    else:
        template = request.args.get('template', template)
        css = request.args.get('css', css)
        if template == 'custom':
            custom_template = True
            template = request.args.get('template-custom', template)
    if not custom_template:
        template_basename, template_ext = os.path.splitext(template)
        if template_ext != '.md':
            template = template_basename + '.md'
    css_basename, css_ext = os.path.splitext(css)
    if css_ext != '.css':
        css = css_basename + '.css'
    # Get their reports.
    root = os.path.join(UPLOADS, uuid)
    if not os.path.isdir(root):
        return redirect(url_for("index", message="Upload error. Try again", **URL_KWARGS))

    reports, molecules = [], []
    for fn in sorted(os.listdir(root)):
        if not os.path.splitext(fn)[1] in ALLOWED_EXTENSIONS:
            continue
        path = os.path.join(root, fn)
        molecule = reporter(path)
        report = molecule.report(template=template, preview=False, process_markdown=True,
                                 web=True)
        reports.append((molecule, report))
        ngl = '{{ viewer3d }}' in report
        with open(os.path.join(root, molecule.basename + '.pdb'), 'w') as f:
            f.write(molecule.pdb_block)

    return render_template('report.html', css=css, uuid=uuid,
                           reports=reports, ngl=ngl, show_NAs=show_NAs)


@app.route("/privacy_policy.html")
def privacy_policy():
    return render_template("privacy_policy.html")


@app.route('/images/<path:filename>')
def get_image(filename):
    return send_from_directory(UPLOADS, filename, as_attachment=True)


def ajax_response(status, msg):
    status_code = "ok" if status else "error"
    return json.dumps(dict(status=status_code, msg=msg))


def clean_uploads():
    for uuid in os.listdir(UPLOADS):
        path = os.path.join(UPLOADS, uuid)
        delta = datetime.datetime.now() - _modification_date(path)
        if delta > datetime.timedelta(hours=1):
            shutil.rmtree(path)


def _modification_date(filename):
    t = os.path.getmtime(filename)
    return datetime.datetime.fromtimestamp(t)


def allowed_filename(*filenames):
    for filename in filenames:
        fn = filename.filename
        if '.' in fn and os.path.splitext(fn)[1].lower() in ALLOWED_EXTENSIONS:
            yield filename