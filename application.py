import os, json

from flask import Flask, session, redirect, render_template, request, jsonify, flash
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from werkzeug.security import check_password_hash, generate_password_hash

import requests

from helpers import login_required

app = Flask(__name__)



app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)



engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

@app.route("/")
@login_required
def index():
    """ Show search box """

    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """ Log user in """
    session.clear()
    username = request.form.get("username")
    if request.method == "POST":
        if not request.form.get("username"):
            return render_template("error.html", message="must provide username")

        
        elif not request.form.get("password"):
            return render_template("error.html", message="must provide password")

       
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                            {"username": username})
        
        result = rows.fetchone()

        if result == None or not check_password_hash(result[2], request.form.get("password")):
            return render_template("error.html", message="invalid username and/or password")
        session["user_id"] = result[0]
        session["user_name"] = result[1]

        return redirect("/")

    else:

        return render_template("login.html")

@app.route("/logout")
def logout():
    """ Log user out """
    session.clear()
    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    """ Register user """
    session.clear()
    if request.method == "POST":
        if not request.form.get("username"):
            return render_template("error.html", message="must provide username")

        userCheck = db.execute("SELECT * FROM users WHERE username = :username",
                          {"username":request.form.get("username")}).fetchone()

        if userCheck:
            return render_template("error.html", message="username already exist")

        
        elif not request.form.get("password"):
            return render_template("error.html", message="must provide password")

        
        elif not request.form.get("confirmation"):
            return render_template("error.html", message="must confirm password")

        
        elif not request.form.get("password") == request.form.get("confirmation"):
            return render_template("error.html", message="passwords didn't match")
        
        
        hashedPassword = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)
        
        
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                            {"username":request.form.get("username"), 
                             "password":hashedPassword})

       
        db.commit()

        flash('Account created', 'info')

        
        return redirect("/login")

    else:

        return render_template("register.html")

@app.route("/search", methods=["GET"])
@login_required
def search():
    """ Get books results """

    
    if not request.args.get("book"):
        return render_template("error.html", message="you must provide a book.")

    
    query = "%" + request.args.get("book") + "%"

    query = query.title()
    
    rows = db.execute("SELECT isbn, title, author, year FROM books WHERE \
                        isbn LIKE :query OR \
                        title LIKE :query OR \
                        author LIKE :query LIMIT 15",
                        {"query": query})
    
    
    if rows.rowcount == 0:
        return render_template("error.html", message="we can't find books with that description.")
    
   
    books = rows.fetchall()

    return render_template("results.html", books=books)

@app.route("/book/<isbn>", methods=['GET','POST'])
@login_required
def book(isbn):
    """ Save user review and load same page with reviews updated."""

    if request.method == "POST":

       
        currentUser = session["user_id"]
        
       
        rating = request.form.get("rating")
        comment = request.form.get("comment")
        
       
        row = db.execute("SELECT id FROM books WHERE isbn = :isbn",
                        {"isbn": isbn})

        bookId = row.fetchone() 
        bookId = bookId[0]

        
        row2 = db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id",
                    {"user_id": currentUser,
                     "book_id": bookId})

       
        if row2.rowcount == 1:
            
            flash('You already submitted a review for this book', 'warning')
            return redirect("/book/" + isbn)

       
        rating = int(rating)

        db.execute("INSERT INTO reviews (user_id, book_id, comment, rating) VALUES \
                    (:user_id, :book_id, :comment, :rating)",
                    {"user_id": currentUser, 
                    "book_id": bookId, 
                    "comment": comment, 
                    "rating": rating})

        
        db.commit()

        flash('Review submitted!', 'info')

        return redirect("/book/" + isbn)
    
   
    else:

        row = db.execute("SELECT isbn, title, author, year FROM books WHERE \
                        isbn = :isbn",
                        {"isbn": isbn})

        bookInfo = row.fetchall()

        """ GOODREADS reviews """

    
        
        
        query = requests.get("https://www.goodreads.com/book/review_counts.json",
                params={"key": "uAlpaYHGVjxcaiFls9uAw", "isbns": isbn})

        
        response = query.json()

        
        response = response['books'][0]

        
        bookInfo.append(response)

        """ Users reviews """

         
        row = db.execute("SELECT id FROM books WHERE isbn = :isbn",
                        {"isbn": isbn})

        
        book = row.fetchone() 
        book = book[0]

       
        results = db.execute("SELECT users.username, comment, rating FROM users JOIN reviews ON users.id = reviews.user_id WHERE book_id = :book ORDER BY time",{"book": book})

        reviews = results.fetchall()

        return render_template("book.html", bookInfo=bookInfo, reviews=reviews)




@app.route("/api/<isbn>", methods=['GET'])
@login_required
def api_call(isbn): 
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    if book is None:
        return render_template("error.html", error_message="We got an invalid isbn. "
                                                           "Please check for the errors and try again.")
    reviews = db.execute("SELECT * FROM reviews WHERE book_id = :book_id", {"book_id": book.id}).fetchall()
    count = 0
    rating = 0
    for review in reviews:
        count += 1
        rating += review.rating
    if count:
        average_rating = rating / count
    else:
        average_rating = 0

    return jsonify(
        title=book.title,
        author=book.author,
        year=book.year,
        isbn=book.isbn,
        review_count=count,
        average_score=average_rating
    )