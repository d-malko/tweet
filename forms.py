from flask_wtf import FlaskForm
from wtforms import (StringField, PasswordField, TextAreaField, IntegerField, SelectField, SelectMultipleField, SubmitField)
from wtforms.validators import (DataRequired, Regexp, ValidationError, Email,
							   Length, EqualTo, NumberRange)

# from models import User

from app import mysql_fetch, mysql_execute, exists_cursor, get_hobbies


def name_exists(form, field):
	query = """SELECT * FROM users WHERE EXISTS (SELECT * FROM users AS t1 WHERE (t1.username = %(username)s)"""
	if exists_cursor(query, {'username': field.data}):
		raise ValidationError('Такой пользователь уже существует.')


def email_exists(form, field):
	query = """SELECT * FROM users WHERE EXISTS (SELECT * FROM users AS t1 WHERE (t1.email = %(email)s))"""
	if exists_cursor(query, {'email': field.data}):
		raise ValidationError('Пользователь с таким адресом почты уже существует.')


class RegisterForm(FlaskForm):
	def __init__(self, *args, **kwargs):
		super(RegisterForm, self).__init__(*args, **kwargs)
		self.hobbies.choices = get_hobbies()

	username = StringField(
		'Имя пользователя',
		validators=[
			DataRequired(),
			Regexp(
				r'^[a-zA-Z0-9_]+$',
				message=("Имя должно состоять только из букв, цыфр и подчеркиваний.")
				),
			name_exists
		])

	second_name = StringField(
		'Фамилия пользователя',
		validators=[
			DataRequired(),
			Regexp(
				r'^[a-zA-Z0-9_]+$',
				message=(
					"Фамилия должна состоять только из букв, цыфр и подчеркиваний.")
			),
			name_exists
		])

	email = StringField(
		'Адрес почты',
		validators=[
			DataRequired(),
			Email(),
			email_exists
		])

	age = IntegerField(
		'Возраст',
		validators=[NumberRange(min=1, max=100)])

	gender = SelectField(
		"Пол",
		choices=[(1, 'жен'), (0, 'муж')],
		validators=[DataRequired()])

	hobbies = SelectMultipleField(
		"Хобби", coerce=int,
		validators=[DataRequired()]
	)

	password = PasswordField(
		'Пароль',
		validators=[
			DataRequired(),
			Length(min=2),
			EqualTo('password2', message='Пароли должны совпадать')
		])

	password2 = PasswordField(
		'Подтвердите пароль',
		validators=[DataRequired()]
	)


class LoginForm(FlaskForm):
	user_email = StringField('Адрес почты/Имя пользователя', validators=[DataRequired()]) #, Email()])
	password = PasswordField('Пароль', validators=[DataRequired()])


class PostForm(FlaskForm):
	content = TextAreaField("Введите сообщение", validators=[DataRequired()])
