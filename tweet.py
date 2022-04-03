from configparser import ConfigParser
from collections import namedtuple
import re

from flask import (
    Flask, g, render_template, flash, redirect, url_for, abort, request
)
from flask_bcrypt import check_password_hash, generate_password_hash
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user, UserMixin
)

from flask_mysqldb import MySQL
from flask_wtf.csrf import CSRFProtect
import forms


DEBUG = True
PORT = 8000

HOST = 'tweet.sredevops.pro'

config = ConfigParser()
config.read('.env')

app = Flask(__name__)
app.secret_key = config['local']['secret_key']
"""here secret_key is a random string of alphanumerics"""

app.config.from_object(
    'config.settings')  # TODO need to deside which will be used

login_manager = LoginManager()
login_manager.init_app(app)

login_manager.login_view = 'login'

csrf = CSRFProtect()
csrf.init_app(app)

mysql = MySQL()




app.config['MYSQL_USER'] = config['local']['user']
app.config['MYSQL_PASSWORD'] = config['local']['password']
app.config['MYSQL_DB'] = config['local']['database']
app.config['MYSQL_CURSORCLASS'] = "DictCursor"
app.config['MYSQL_HOST'] = '127.0.0.1'
app.config['MYSQL_PORT'] = 3306
mysql.init_app(app)




@app.before_request
def before_request():
    """Connect to database before each request
    g is a global object, passed around all time in flask, used to setup things which
    we wanna have available everywhere.
    """
    g.db = mysql.connect
    g.user = current_user


@app.after_request
def after_request(response):
    """close all database connection after each request"""
    g.db.close()
    return response


#TODO concat two functions (return id)
def exists_cursor(query, values):
    try:
        cursor = g.db.cursor()
        result = cursor.execute(query, values)
        return bool(result)
    except Exception as e:
        print("Problem getting values from db: " + str(e))
        return False
        # con.cl


def mysql_execute(query, values) -> object: #TODO rename
    try:
        # cursor, connection = db_connection()
        cursor = g.db.cursor()
        cursor.execute(query, values)
        g.db.commit()
        return cursor.lastrowid #TODO
    except cursor.Error as e:
        print(e)
        return False
    except Exception as e:
        print("Problem inserting into db: " + str(e))
        return False


def mysql_fetch(query, values=(), count='one') -> list or dict:
    cursor = g.db.cursor()
    cursor.execute(query, values)
    if count == 'one':
        result = cursor.fetchone()
    elif count == 'all':
        result = cursor.fetchall()
    if isinstance(result, tuple):
        return list(result)
    else:
        return result


def get_hobbies():
    query = '''SELECT id, name FROM hobbies'''
    result = mysql_fetch(query, count='all')
    hobbies = []
    if result:
        hobbies = [(_['id'], _['name']) if _ else () for _ in result]
    return hobbies


def get_posts(user_id=None):
    result = list()
    if user_id:
        query = '''SELECT id, timestamp, user_id, content FROM posts WHERE user_id = %(user_id)s LIMIT 100 '''
    else:
        query = '''SELECT id, timestamp, user_id, content FROM posts LIMIT 100 '''
    posts = mysql_fetch(query, {'user_id': user_id}, count='all')
    if posts:
        for post in posts:
            result.append(create_dyn_class_obj('Post', post))
    return result


def get_user(request_values) -> object:
    fields = {'id', 'username', 'email'}
    request_keys = fields & set(request_values.keys())
    string = ""
    for i, field in enumerate(request_keys):
        string += f"{field} = %({field})s"
        if len(request_keys) > 1 and i != len(request_keys) - 1:
            string += ' OR '
    query = f"SELECT id, username, second_name, age, gender, email, password, joined_at, is_active, is_admin FROM users WHERE {string}"
    account = mysql_fetch(query, request_values)
    if account:
        user = create_dyn_class_obj('User', account)
        user.hobbies = user.get_hobbies()
        return user

    else:
        return None


class UserBaseClass:
    def get_id(self):
        return self.id

    def __eq__(self, other):
        return self.username == other

    def __contains__(self, item):
        return True

    def get_posts(self) -> list:
        """Get all user's posts"""
        result = list()
        query = '''SELECT id, timestamp, user_id, content FROM posts WHERE user_id = %(user_id)s LIMIT 100 '''
        posts = mysql_fetch(query, {'user_id': self.id}, count='all')
        if posts:
            for post in posts:
                result.append(create_dyn_class_obj('Post', post))
        return result

    def get_hobbies(self):
        result = list()
        query = '''SELECT t3.id, t3.name
                FROM users t1
                INNER JOIN users_hobbies t2 on t1.id = t2.user_id
                INNER JOIN hobbies t3 on t2.hobby_id = t3.id
                WHERE t1.id = %(user_id)s LIMIT 100 
                '''
        hobbies = mysql_fetch(query, {'user_id': self.id}, count='all')
        if hobbies:
            for hobby in hobbies:
                result.append(create_dyn_class_obj('Hobby', hobby))
        return hobbies

    def get_stream(self):
        """Get all subscribed posts"""
        result = list()
        query = """
            select * from posts as t1 where (
                t1.user_id in (
                    SELECT t2.id
                    from users AS t2
                        JOIN
                        relationships as t3 ON (
                            t3.to_user_id = t2.id
                            )
                    where t3.from_user_id = %(user_id)s
                    )
                ) LIMIT 100;
            """  # TODO check if it's working
        posts = mysql_fetch(query, {'user_id': self.id}, count='all')
        if posts:
            for post in posts:
                result.append(create_dyn_class_obj('Post', post))
        return result


    def following(self):
        """The users we are following"""
        result = list()
        query = """
            SELECT t1.username from users AS t1
                JOIN
                    relationships as t2 ON (
                        t2.to_user_id = t1.id
                    ) where t2.from_user_id = %(user_id)s;
                """
        users = mysql_fetch(query, {
            'user_id': self.id
        }, count='all')
        for user in users:
            result.append(create_dyn_class_obj('User', user))
        return result

    def followers(self):
        """Users Following the current user"""
        result = list()
        query = """
            SELECT t1.username from users AS t1
                JOIN
                    relationships as t2 ON (
                        t2.from_user_id = t1.id
                    ) where t2.to_user_id = %(user_id)s;
        """
        users = mysql_fetch(query, {
            'user_id': self.id
        }, count='all')
        for user in users:
            result.append(create_dyn_class_obj('User', user))
        return result


def create_dyn_class_obj(class_name, class_args) -> object:
    BaseClass = namedtuple(class_name, class_args.keys())
    if class_name == 'User':
        Class = type(class_name, (UserBaseClass, BaseClass, UserMixin), {})
        Class(**class_args)
    elif class_name == 'Post':
        Class = type(class_name, (BaseClass,), {})
        post = Class(**class_args)
        post.user = get_user({'id': post.user_id})
        return post
    else:
        Class = type(class_name, (BaseClass,), {})
    return Class(**class_args)


@login_manager.user_loader
def load_user(userid):
    try:
        return get_user({'id': userid})
    except TypeError as e:
        print(e)
        return None


@app.route('/register', methods=('GET', 'POST'))
def register():
    form = forms.RegisterForm()
    if form.validate():
        username = request.form['username']
        second_name = request.form['second_name']
        password = request.form['password']
        email = request.form['email']
        password = generate_password_hash(password).decode()
        request_values = {'username': username, 'email': email}
        account = get_user(request_values)  #TODO
        print(form.hobbies)
        if account is not None:
            flash(f'Пользователь {username} {second_name} уже существует', "error")
        if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash(f'Введите корректное название почты', "error")
        elif not re.match(r'[A-Za-z0-9_]+', username):
            flash(f'Название почты может включать только буквы, цифры и нижнее подчеркивание', "error")
        elif not username or not password or not email:
            flash('Пожалуйста заполните форму', "error")
        else:
            query = """INSERT INTO users ( username, second_name, email, password, gender, age, is_active)
            values (%(username)s, %(second_name)s, %(email)s, %(password)s, %(gender)s, %(age)s, %(is_active)s)"""
            values = {
                'username': username,
                'second_name': form.second_name.data,
                'email': email,
                'password': password,
                'gender': form.gender.data,
                'age': form.age.data,
                'is_active': bool(True)
            }
            user_id = mysql_execute(query, values)
            insert_request = f"""INSERT INTO users_hobbies (user_id, hobby_id) values ({user_id}, {form.hobbies.data.pop(0)})"""

            for _ in form.hobbies.data:
                insert_request = insert_request + f", ({user_id}, {_})"
            hobby_values = {
                "username": username,
                "second_name": second_name
            }
            mysql_execute(insert_request, hobby_values)
            if user_id:
                values['id'] = user_id
                user = create_dyn_class_obj('User', values)
                login_user(user)
                flash(f"{username} успешно зарегистрирован!", "success")
                return redirect(url_for('index'))
    else:
        flash(f"Ошибка при регистрации пользователя ", "error")
    return render_template('register.html', form=form)


@app.route('/login', methods=('GET', 'POST'))
def login():
    form = forms.LoginForm()
    if form.validate_on_submit():
        if re.match(r'[^@]+@[^@]+\.[^@]+', form.user_email.data):
            request_key = 'email'
        else:
            request_key = 'username'
        user = get_user({request_key: form.user_email.data})

        if getattr(user, 'username'):  # TODO change to is not None
            if getattr(user, request_key) != form.user_email.data:
                flash("Адрес почты не совпадает", "error")
            elif not check_password_hash(user.password, form.password.data):
                flash("Неправильный пароль", "error")
            else:
                login_user(user)
                """Creating a session on user's browser"""
                flash(f"{user.username}, добро пожаловать!", "success")
                return redirect(url_for('index'))
        else:
            flash(f"Пользователь {form.email.data} не найден", "error")

    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Вы вышли.")
    return redirect(url_for('login'))


@app.route('/')
def index():
    return render_template('stream.html', stream=get_posts())


@app.route('/new_post', methods=('GET', 'POST'))
@login_required
def post():
    form = forms.PostForm()
    if form.validate():
        query = """
        INSERT INTO posts (user_id, content)
        values (%(user_id)s, %(content)s)
        """
        if mysql_execute(query, {'user_id': g.user.id, 'content': form.content.data}):
            flash("Сообщение создано", "success")
            return redirect(url_for('index'))
    return render_template('post.html', form=form)


@app.route('/stream')
@app.route('/stream/<username>')
def stream(username=None):
    template = 'stream.html'
    stream = list()
    if username and (
            current_user.is_anonymous or username != current_user.username):
        try:
            user = get_user({'username': username})
            if user is not None:
                user_id = user.id
        except Exception:
            abort(404)
        else:
            query = """SELECT t1.id, t1.timestamp, t1.user_id, t1.content FROM posts AS t1 WHERE (t1.user_id = %(user_id)s) LIMIT 100"""
            posts = mysql_fetch(query, {'user_id': user_id}, count='all') #TODO rewrite this code
            if posts:
                for post in posts:
                    stream.append(create_dyn_class_obj('Post', post))

    else:
        user = current_user
        stream = user.get_stream()
        user.posts = stream
    if username:
        template = 'user_stream.html'
    return render_template(template, stream=stream, user=user)


@app.route('/post/<int:post_id>')
def view_post(post_id):
    stream = list()
    query = """SELECT t1.id, t1.timestamp, t1.user_id, t1.content FROM posts AS t1 WHERE (t1.id = %(id)s)"""
    posts = mysql_fetch(query, {"id": post_id}, count='all')
    if posts:
        for post_obj in posts:
            stream.append(create_dyn_class_obj('Post', post_obj))
    else:
        abort(404)

    return render_template('stream.html', stream=stream)


@app.route('/follow/<username>')
@login_required
def follow(username):
    if username == current_user.username:
        flash("Невозможно подписаться на себя")
    else:
        to_user = get_user({'username': username})
        query = """
                INSERT INTO relationships (from_user_id, to_user_id)
                values (%(from_user)s, %(to_user)s)
                """
        if mysql_execute(query,
                         {'from_user': g.user.id, 'to_user': to_user.id}):
            flash("You are now following {}".format(to_user.username),
                  "success")
    return redirect(url_for('stream', username=to_user.username))


@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    to_user = get_user({'username': username})
    print(g.user._get_current_object())
    query = """
        DELETE FROM relationships WHERE from_user_id = %(from_user)s AND to_user_id = %(to_user)s
        """
    if mysql_execute(query,
                     {'from_user': g.user.id, 'to_user': to_user.id}):
        flash("Вы отписались {}".format(to_user.username), "success")
    return redirect(url_for('stream', username=to_user.username))


@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


# if __name__ == '__main__':
    app.run(debug=DEBUG, host=HOST)

