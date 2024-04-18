import mysql.connector
from email_validator import validate_email, EmailNotValidError
import sys
from stdiomask import getpass
from passlib.hash import sha256_crypt
from config import config

config['database'] = 'odms'
try:
    conn = mysql.connector.connect(**config)
    cur = conn.cursor()
except mysql.connector.Error as e:
    print(
        f"Something went wrong while accessing the database: {str(e)}", file=sys.stderr
    )


print("-------------------------------")

name = input("Full name: ")
username = input("Username: ")
email = input("Email: ")

try:
    valid = validate_email(email)
    email = valid.email
except EmailNotValidError as e:
    print(str(e), file=sys.stderr)
    exit(1)

password = getpass("Password: ")

if len(password) < 8:
    print("The password length needs to be at least 8.", file=sys.stderr)
    exit(1)

print("-------------------------------")

cur.execute(
    "INSERT INTO users(name, username, email, password, admin) VALUES (%s, %s, %s, %s, %s)",
    (name, username, email, sha256_crypt.hash(password), 1),
)
conn.commit()
cur.close()
conn.close()

print("New user successfully created.")
