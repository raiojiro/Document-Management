from flask import (
    Flask,
    request,
    render_template,
    redirect,
    session,
    url_for,
    abort,
    send_file,
    flash,
)
from mysql.connector.connection import MySQLConnection
from passlib.hash import sha256_crypt
from mysql.connector import errorcode
from werkzeug.utils import secure_filename, send_from_directory
from functools import wraps
from decorator import login_required, admin_required
import zipfile, shutil, os, mysql.connector, time, io
from datetime import datetime
from config import config, base_path

app = Flask(__name__)
app.secret_key = "random"

DB_NAME = "odms"
TABLES = {}
TABLES["users"] = (
    "CREATE TABLE IF NOT EXISTS users ("
    "name VARCHAR(100) UNIQUE,"
    "username VARCHAR(50) UNIQUE,"
    "email VARCHAR(50) UNIQUE,"
    "password VARCHAR(100),"
    "admin BOOLEAN"
    ") ENGINE = InnoDB"
)
TABLES[
    "files"
] = "CREATE TABLE IF NOT EXISTS files (file TEXT, date VARCHAR(50)) ENGINE = InnoDB"
con = ""
cur = ""


def list_path(pathA):
    if session["admin"] == 1:
        files = os.listdir(os.path.join(base_path, pathA))
    else:
        files = os.listdir(os.path.join(base_path, session["name"], pathA))
    return files


def semester_sort(semesters):
    SORT_ORDER = {"AUG": 0, "MAY": 1, "JAN": 2}
    semesters.sort(key=lambda x: (x[-4:], SORT_ORDER), reverse=True)
    return semesters


def fileEmpty(path):
    file_path = os.path.join(base_path, path)
    if os.listdir(file_path) == []:
        return True
    else:
        return False


def isDir(path, file):
    file_path = os.path.join(base_path, session["name"], path[1:], file)
    if os.path.isdir(file_path):
        return True
    else:
        return False


def filesNum(path):
    totalDir = 1
    if session["admin"] == 1:
        full_path = os.path.join(base_path, path)
    else:
        full_path = os.path.join(base_path, session["name"], path)
    for root, dirs, files in os.walk(full_path):
        for name in dirs:
            totalDir += 1
    return totalDir


app.jinja_env.globals.update(
    list_path=list_path,
    isDir=isDir,
    filesNum=filesNum,
    fileEmpty=fileEmpty,
    semester_sort=semester_sort,
)


@app.errorhandler(404)
def error(e):
    return render_template("error.html", e=e)


def logged_in():
    if "username" in session:
        return redirect(url_for("main"))


def init_db():
    global con
    global cur
    try:
        con = mysql.connector.connect(**config)
        cur = con.cursor()
    except mysql.connector.Error as e:
        error(e)


def close_db():
    if con.is_connected:
        con.close()


def checkDatabase():
    global config

    try:
        cnx = mysql.connector.connect(**config)
        cursor = cnx.cursor()
    except mysql.connector.Error as e:
        error(e)
        exit(1)

    try:
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS {} DEFAULT CHARACTER SET 'utf8'".format(
                DB_NAME
            )
        )
    except mysql.connector.Error as err:
        print("Failed creating database: {}".format(err))
        exit(1)

    try:
        cursor.execute("USE {}".format(DB_NAME))
    except mysql.connector.Error as err:
        print("Database {} does not exists.".format(DB_NAME))
        if err.errno == errorcode.ER_BAD_DB_ERROR:
            checkDatabase(config)
            print("Database {} created successfully.".format(DB_NAME))
            cnx.database = DB_NAME
        else:
            print(err)
            exit(1)

    for table_name in TABLES:
        table_description = TABLES[table_name]
        try:
            print("Creating table {}: ".format(table_name), end="")
            cursor.execute(table_description)
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
                print("already exists.")
            else:
                print(err.msg)
        else:
            print("OK")

    cursor.close()
    cnx.close()
    config['database'] = DB_NAME

    if not os.path.exists(base_path):
        os.mkdir(base_path)


@app.route("/", methods=["GET", "POST"], defaults={"path": ""})
@app.route("/<path:path>", methods=["GET", "POST"])
@login_required
def main(path):
    if session["admin"] == 1:
        return redirect(url_for("home_admin", path=path))
    else:
        BASE_DIR = os.path.join(base_path, session["name"])
        if path == "main":
            abs_path = BASE_DIR
        else:
            if path.startswith("main/"):
                return redirect(path[4:])
            abs_path = os.path.join(BASE_DIR, path)
    if request.method == "POST":
        if request.form.get("submit") == "new_folder":
            folder = request.form["folder_name"]
            filepath = os.path.join(abs_path, folder)
            if not os.path.exists(filepath):
                os.mkdir(filepath)
        elif request.form.get("submit") == "download":
            filename = request.form.get("filename")
            filepath = os.path.join(abs_path, filename)
            if os.path.isdir(filepath):
                timestr = time.strftime("%d%m%Y")
                fileName = filename + "_{}.zip".format(timestr)
                memory_file = io.BytesIO()
                with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(filepath):
                        for file in files:
                            arcname = filename + '/' + file
                            zipf.write(os.path.join(root, file), arcname)
                memory_file.seek(0)
                return send_file(
                    memory_file, download_name=fileName, as_attachment=True
                )
            else:
                return send_file(filepath, as_attachment=True)
        elif request.form.get("submit") == "del_file":
            filename = request.form.get("filename")
            filepath = os.path.join(abs_path, filename)
            if os.path.exists(filepath):
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    init_db()
                    try:
                        cur.execute(
                            "DELETE FROM files WHERE file = %s",
                            (session["name"] + "/" + path + "/" + filename,),
                        )
                        con.commit()
                    except mysql.connector.Error as e:
                        return error(e)
                    close_db()
                elif os.path.isdir(filepath):
                    shutil.rmtree(filepath)
        else:
            semester = (
                request.form.get("semester_month") + " " + request.form["semester_year"]
            )
            subjects = [
                request.form["sub1"],
                request.form["sub2"],
                request.form["sub3"],
                request.form["sub4"],
            ]
            semesterDir = os.path.join(BASE_DIR, semester)
            for subject in subjects:
                if subject:
                    subDir = os.path.join(semesterDir, subject)
                    directory = ["Quiz", "Test", "Assignment", "Final Exam"]
                    for x in directory:
                        if not os.path.exists(os.path.join(subDir, x)):
                            os.makedirs(os.path.join(subDir, x))
    

    if not os.path.exists(abs_path):
        return error(abs_path)
    dates = {}
    if os.path.isfile(abs_path):
        return send_file(abs_path)

    files = os.listdir(abs_path)
    for file in files:
        if os.path.isfile(os.path.join(abs_path, file)):
            file_path = session["name"] + "/" + path + "/" + file
            init_db()
            try:
                cur.execute("SELECT * FROM files WHERE file = %s", (file_path,))
                dates[file_path] = cur.fetchone()
            except mysql.connector.Error as e:
                return error(e)

    return render_template("home.html", files=files, dates=dates)


@app.route("/login", methods=["GET", "POST"])
def login():
    logged_in()
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        e = "There has been a problem during your login. Send an email to example@example.com for help."

        init_db()

        try:
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            result = cur.fetchone()
        except mysql.connector.Error as e:
            return error(e)

        close_db()

        if result is None:
            flash("Account not registered")
        elif not sha256_crypt.verify(password, result[3]):
            flash("Wrong password")
        else:
            session["username"] = username
            session["name"] = result[0]
            session["admin"] = result[4]
            if result[4] == 0:
                return redirect(url_for("main"))
            elif result[4] == 1:
                return redirect(url_for("home_admin"))
            else:
                return error("Admin not set")
    return render_template("login.html")


@app.route("/register")
def register():
    logged_in()
    return render_template("register.html")


@app.route("/register2", methods=["POST"])
def register2(email=None):
    logged_in()
    init_db()
    email = request.form["email"]
    try:
        cur.execute("SELECT name, username FROM users WHERE email = %s", (email,))
        result = cur.fetchone()
    except mysql.connector.Error as e:
        return error(e)
    close_db()
    if result is None:
        flash("The user is not registered by admin")
        return redirect(url_for("register"))
    elif result[1]:
        flash("The user has already made an account")
        return redirect(url_for("register"))
    return render_template("register2.html", name=result, email=email)


@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("name", None)
    session.pop("admin", None)
    return redirect(url_for("login"))


@app.route("/settings")
@login_required
def settings():
    name = session["name"]
    init_db()
    try:
        cur.execute("SELECT * FROM users WHERE name = %s", (name,))
        result = cur.fetchone()
    except mysql.connector.Error as e:
        return error(e)

    close_db()

    return render_template("settings.html", result=result)


@app.route("/handle_settings", methods=["POST"])
@login_required
def handle_settings():

    old_user = session["username"]
    old_name = session["name"]
    name = request.form["name"]
    user = request.form["username"]
    email = request.form["email"]
    password = request.form["password"]

    if not password:
        db = "UPDATE users SET name = %s, username = %s, email = %s WHERE username = %s"
        var = (name, user, email, old_user)
    else:
        db = "UPDATE users SET name = %s, username = %s, email = %s, password = %s WHERE username = %s"
        var = (name, user, email, password, old_user)

    init_db()
    try:
        cur.execute(db, var)
        con.commit()
    except mysql.connector.IntegrityError:
        close_db()
        flash('The name/username/email is already taken')
        return redirect(url_for("settings"))
    except mysql.connector.Error as e:
        return error(e)
    

    close_db()
    session["name"] = name
    session["username"] = user

    new_path = os.path.join(base_path, name)
    old_path = os.path.join(base_path, old_name)

    if (os.path.isdir(old_path)):
        os.rename(old_path, new_path)
    else:
        os.mkdir(new_path)
    flash('Account successfully modified')
    return redirect(url_for("settings"))


@app.route("/handle_register", methods=["POST"])
def handle_register():
    logged_in()
    name = request.form["name"]
    email = request.form["email"]
    username = request.form["username"]
    password = sha256_crypt.hash(request.form["password"])
    init_db()
    try:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        result = cur.fetchone()
    except mysql.connector.Error as e:
        return error(e)

    if result is not None:
        flash("The username is already taken")
        return redirect(url_for("register2"), code=307)

    try:
        cur.execute(
            "UPDATE users SET username=%s, password=%s, admin=%s WHERE email = %s",
            (username, password, False, email),
        )
        con.commit()
    except mysql.connector.Error as e:
        return error(e)
    path = os.path.join(base_path, name)
    os.mkdir(path)
    close_db()

    return redirect(url_for("login"))


@app.route("/handle_upload", methods=["POST"])
def handle_upload():
    name = session["name"]
    path = request.form["path"]
    path = path[1:]
    app.config["UPLOAD_FOLDER"] = os.path.join(base_path, name, path)
    file = request.files["fileup"]
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    init_db()
    try:
        today = datetime.now()
        cur.execute(
            "INSERT INTO files(file, date) VALUES (%s, %s)",
            (name + "/" + path + "/" + filename, today.strftime("%d/%m/%Y")),
        )
        con.commit()
    except mysql.connector.Error as e:
        return error(e)
    close_db()
    return redirect(url_for("main", path=path))


@app.route("/admin")
@login_required
@admin_required
def home_admin():

    if not os.path.exists(base_path):
        return error(404)

    if os.path.isfile(base_path):
        return send_file(base_path)

    files = os.listdir(base_path)

    return render_template("home_admin.html", files=files, semesters={}, subjects={})


@app.route("/admin/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_admin():
    init_db()
    if request.method == "POST":
        name = request.form.get("hidden_name")
        if request.form.get("submit") == "delete":
            try:
                cur.execute(
                    "DELETE FROM users WHERE email = %s",
                    (request.form.get("hidden_email"),),
                )
                con.commit()
            except mysql.connector.Error as e:
                return render_template(error.html, e)
            if os.path.isdir(os.path.join(base_path, name)):
                shutil.rmtree(os.path.join(base_path, name))
        elif request.form.get("submit") == "editUser":
            return redirect(url_for("edit_admin", name = name))
    try:
        cur.execute("SELECT name, username, email FROM users ORDER BY name")
        users = cur.fetchall()
    except mysql.connector.Error as e:
        error(e)

    close_db()
    return render_template("add_admin.html", users=users)


@app.route("/admin/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_admin():
    init_db()
    if request.method == "POST":
        init_name = request.form.get("hidden_name")
        name = request.form["name"]
        user = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        if not password:
            db = "UPDATE users SET name = %s, username = %s, email = %s WHERE name = %s"
            var = (name, user, email, init_name)
        else:
            db = "UPDATE users SET name = %s, username = %s, email = %s, password = %s WHERE name = %s"
            var = (name, user, email, password, init_name)
        try:
            cur.execute(db, var)
            con.commit()
        except mysql.connector.IntegrityError:
            close_db()
            flash('The name/username/email is already taken')
            return redirect(url_for("edit_admin"), code = 302)
        except mysql.connector.Error as e:
            return error(e)
        if os.path.exists(os.path.join(base_path, init_name)):
            os.rename(os.path.join(base_path, init_name), os.path.join(base_path, name))
        flash('Account successfully modified')
    else:
        name = request.args.get("name")
    try:
        cur.execute("SELECT * FROM users WHERE name = %s", (name,))
        result = cur.fetchone()
    except mysql.connector.Error as e:
        return error(e)

    close_db()
    
    return render_template("edit_admin.html", result=result)


@app.route("/admin/add/form", methods=["GET", "POST"])
@login_required
@admin_required
def add_admin_form():
    if request.method == "POST":
        init_db()
        try:
            cur.execute(
                "SELECT * FROM users WHERE name = %s OR email = %s",
                (request.form["name"], request.form["email"]),
            )
            result = cur.fetchone()
        except mysql.connector.Error as e:
            error(e)
        if result is None:
            try:
                cur.execute(
                    "INSERT INTO users(name, email) VALUES (%s, %s)",
                    (request.form["name"], request.form["email"]),
                )
                con.commit()
            except mysql.connector.Error as e:
                error(e)
            flash("User successfully registered")
        else:
            flash("User already registered previously")

        close_db()

    return render_template("add_admin_form.html")


@app.route("/admin/files", defaults={"path": ""}, methods=["GET", "POST"])
@app.route("/admin/files/<path:path>", methods=["GET", "POST"])
@login_required
@admin_required
def files_admin(path):
    abs_path = os.path.join(base_path, path)
    if not os.path.exists(abs_path):
        return error(404)

    if os.path.isfile(abs_path):
        return send_file(abs_path)

    files = os.listdir(abs_path)
    dates = {}
    for file in files:
        if os.path.isfile(os.path.join(abs_path, file)):
            file_path = path + "/" + file
            init_db()
            try:
                cur.execute("SELECT * FROM files WHERE file = %s", (file_path,))
                dates[file_path] = cur.fetchone()
                print(dates[file_path])
            except mysql.connector.Error as e:
                return error(e)

    if request.method == "POST":
        if request.form.get("submit") == "download":
            filename = request.form.get("filename")
            filepath = os.path.join(abs_path, filename)
            if os.path.isdir(filepath):
                timestr = time.strftime("%d%m%Y")
                fileName = filename + "_{}.zip".format(timestr)
                memory_file = io.BytesIO()
                with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(filepath):
                        for file in files:
                            arc_path = filename + "/" + file
                            zipf.write(os.path.join(root, file), arc_path)
                memory_file.seek(0)
                return send_file(
                    memory_file, download_name=fileName, as_attachment=True
                )
            else:
                return send_file(filepath, as_attachment=True)
        elif request.form.get("submit") == "del_file":
            filename = request.form.get("filename")
            filepath = os.path.join(abs_path, filename)
            if os.path.exists(filepath):
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    init_db()
                    try:
                        cur.execute(
                            "DELETE FROM files WHERE file = %s",
                            (abs_path + "/" + filename,),
                        )
                        con.commit()
                    except mysql.connector.Error as e:
                        return error(e)
                    close_db()
                elif os.path.isdir(filepath):
                    shutil.rmtree(filepath)

    return render_template("files_admin.html", files=files, dates=dates)


@app.route("/admin/search")
@login_required
@admin_required
def search():
    keyword = request.args.get("keyword")
    files = []
    semesters = {}
    subjects = {}
    for file in os.listdir(base_path):
        if keyword.lower() in file.lower():
            files.append(file)
        for semester in os.listdir(os.path.join(base_path, file)):
            if keyword.lower() in semester.lower():
                try:
                    semesters[file].append(semester)
                except KeyError:
                    files.append(file)
                    semesters[file] = []
                    semesters[file].append(semester)
    return render_template(
        "home_admin.html", files=files, semesters=semesters, subjects=subjects
    )


if __name__ == "__main__":
    checkDatabase()
    app.run()
