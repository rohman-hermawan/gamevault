import os
import tempfile
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from storage import MinioStorage, StorageError

load_dotenv()

ALLOWED_EXTENSIONS = {"mp4", "webm", "mkv", "mov", "avi"}
MAX_UPLOAD_GB = int(os.getenv("MAX_UPLOAD_GB", "2"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_GB * 1024 * 1024 * 1024

storage = MinioStorage.from_environment()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def human_size(size_bytes: int) -> str:
    size = float(size_bytes or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


app.jinja_env.filters["human_size"] = human_size
app.jinja_env.filters["urlquote"] = lambda value: quote(str(value), safe="")


@app.get("/")
def index():
    query = request.args.get("q", "").strip()
    try:
        videos = storage.list_videos(query=query)
        total_size = sum(item["size"] for item in videos)
        return render_template(
            "index.html",
            videos=videos,
            total_size=total_size,
            query=query,
            storage_error=None,
        )
    except StorageError as exc:
        return render_template(
            "index.html",
            videos=[],
            total_size=0,
            query=query,
            storage_error=str(exc),
        )


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    video_file = request.files.get("video")
    title = request.form.get("title", "").strip()
    game = request.form.get("game", "").strip()
    category = request.form.get("category", "Gameplay").strip() or "Gameplay"
    description = request.form.get("description", "").strip()

    if not video_file or not video_file.filename:
        flash("Pilih file video terlebih dahulu.", "error")
        return render_template("upload.html", form=request.form)

    if not allowed_file(video_file.filename):
        flash("Format file tidak didukung. Gunakan MP4, WEBM, MKV, MOV, atau AVI.", "error")
        return render_template("upload.html", form=request.form)

    safe_filename = secure_filename(video_file.filename)
    if not safe_filename:
        flash("Nama file tidak valid.", "error")
        return render_template("upload.html", form=request.form)

    if not title:
        title = Path(safe_filename).stem.replace("_", " ").replace("-", " ").title()

    temp_path = None
    try:
        suffix = Path(safe_filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            video_file.save(temp_file)

        storage.upload_video(
            file_path=temp_path,
            original_filename=safe_filename,
            title=title,
            game=game,
            category=category,
            description=description,
        )
        flash("Video gameplay berhasil diunggah ke MinIO S3.", "success")
        return redirect(url_for("index"))
    except StorageError as exc:
        flash(str(exc), "error")
        return render_template("upload.html", form=request.form)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/watch/<path:object_name>")
def watch(object_name: str):
    try:
        video = storage.get_video(object_name)
        stream_url = storage.presigned_url(object_name, download=False)
        return render_template("watch.html", video=video, stream_url=stream_url)
    except StorageError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))


@app.get("/download/<path:object_name>")
def download(object_name: str):
    try:
        return redirect(storage.presigned_url(object_name, download=True))
    except StorageError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))


@app.post("/delete/<path:object_name>")
def delete(object_name: str):
    try:
        storage.delete_video(object_name)
        flash("Video berhasil dihapus dari bucket.", "success")
    except StorageError as exc:
        flash(str(exc), "error")
    return redirect(url_for("index"))


@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(_error):
    flash(f"Ukuran file melebihi batas {MAX_UPLOAD_GB} GB.", "error")
    return redirect(url_for("upload"))


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
