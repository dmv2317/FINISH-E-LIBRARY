import os
from flask import Flask, abort, render_template, redirect, send_file, send_from_directory, url_for, request, flash, jsonify # type: ignore
from flask_sqlalchemy import SQLAlchemy # type: ignore
from flask_bcrypt import Bcrypt # type: ignore
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user # type: ignore
from flask_wtf import FlaskForm # type: ignore
from wtforms import StringField, TextAreaField, FileField, SubmitField, SelectField # type: ignore # type: ignore
from wtforms.validators import DataRequired # type: ignore
from flask_wtf.csrf import CSRFProtect # type: ignore
from flask_cors import CORS # type: ignore
from werkzeug.utils import secure_filename # type: ignore
from datetime import datetime

app = Flask(__name__)

feedbacks = []

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = "supersecretkey"
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Extensions
csrf = CSRFProtect(app)
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
CORS(app)

# Flask-Login Setup
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# User Model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    feedbacks = db.relationship('Feedback', backref='user', lazy=True)
    ratings = db.relationship('BookRating', backref='user', lazy=True)

# Book Model
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)  # Field for book cover image
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ratings = db.relationship('BookRating', backref='book', lazy=True)
    
    @property
    def average_rating(self):
        if not self.ratings:
            return 0
        return sum(rating.rating for rating in self.ratings) / len(self.ratings)

class FeedbackForm(FlaskForm):
    feedback_type = SelectField("Feedback Type", choices=[
        ('general', 'General Feedback'),
        ('book_review', 'Book Review'),
        ('suggestion', 'Suggestion'),
        ('complaint', 'Complaint')
    ], validators=[DataRequired()])
    book_id = SelectField("Select Book", coerce=int)  # No validators for optional field
    rating = SelectField("Rating", choices=[(0, 'Not Rated'), (1, '1 Star'), (2, '2 Stars'), 
                                        (3, '3 Stars'), (4, '4 Stars'), (5, '5 Stars')], 
                     coerce=int)  # No validators for optional field
    message = TextAreaField("Your Feedback", validators=[DataRequired()])
    submit = SubmitField("Submit Feedback")

def migrate_database():
    with app.app_context():
        # Check if the columns exist
        import sqlite3
        try:
            conn = sqlite3.connect('instance/users.db')
            cursor = conn.cursor()
            
            # Check book table columns
            cursor.execute('PRAGMA table_info(book)')
            book_columns = [column[1] for column in cursor.fetchall()]
            
            # If image_url column doesn't exist, add it
            if 'image_url' not in book_columns:
                cursor.execute('ALTER TABLE book ADD COLUMN image_url VARCHAR(500)')
                conn.commit()
                print("Added image_url column to book table")
            
            # Check if BookRating table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='book_rating'")
            if not cursor.fetchone():
                # Create BookRating table
                cursor.execute('''
                CREATE TABLE book_rating (
                    id INTEGER PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL,
                    created_at TIMESTAMP,
                    FOREIGN KEY (book_id) REFERENCES book (id),
                    FOREIGN KEY (user_id) REFERENCES user (id),
                    UNIQUE (book_id, user_id)
                )
                ''')
                conn.commit()
                print("Created BookRating table")
            
            # Check if Feedback table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
            if not cursor.fetchone():
                # Create Feedback table
                cursor.execute('''
                CREATE TABLE feedback (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    book_id INTEGER,
                    feedback_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    rating INTEGER,
                    created_at TIMESTAMP,
                    FOREIGN KEY (book_id) REFERENCES book (id),
                    FOREIGN KEY (user_id) REFERENCES user (id)
                )
                ''')
                conn.commit()
                print("Created Feedback table")
            
            conn.close()
        except Exception as e:
            print(f"Migration error: {e}")

# Book Rating Model
class BookRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 star rating
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Ensure a user can only rate a book once
    __table_args__ = (db.UniqueConstraint('book_id', 'user_id', name='unique_book_user_rating'),)

# Feedback Model
class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=True)  # Optional, for book-specific feedback
    feedback_type = db.Column(db.String(50), nullable=False)  # 'general', 'book_review', 'suggestion', 'complaint'
    message = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=True)  # For book reviews
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add relationship to book
    book = db.relationship('Book', backref='feedbacks', lazy=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Book Upload Form
class BookUploadForm(FlaskForm):
    book_name = StringField("Book Name", validators=[DataRequired()])
    author = StringField("Author", validators=[DataRequired()])
    category = SelectField("Category", choices=[
        ('Fantasy', 'Fantasy'),
        ('Science', 'Science'),
        ('fiction', 'fiction'),
        ('biographies', 'biographies'),
        ('history','history'),
        ('mystery', 'mystery'),
        ('comics', 'comics'),
        ('astronomy', 'astronomy'),
        ('technology', 'technology'),
        ('medical science', 'medical science')
    ], validators=[DataRequired()])
    description = TextAreaField("Description")
    image_url = StringField("Book Cover URL")  # Field for book cover image
    book = FileField("Book", validators=[DataRequired()])
    submit = SubmitField("Upload")


@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not username or not email or not password or not confirm_password:
            flash("All fields are required!", "danger")
            return redirect(url_for('register'))

        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "danger")
            return redirect(url_for('register'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, email=email, password_hash=hashed_password)

        db.session.add(new_user)
        db.session.commit()

        flash("Account created! Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for('home'))
        else:
            flash("Invalid credentials!", "danger")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/home')
@login_required
def home():
    # Get top-rated books
    top_rated_books = Book.query.join(BookRating).group_by(Book.id).order_by(db.func.avg(BookRating.rating).desc()).limit(5).all()
    return render_template('home.html', username=current_user.username, top_rated_books=top_rated_books)

@app.route('/about')
@login_required
def about():
    return render_template('about.html', username=current_user.username)

@app.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback():
    form = FeedbackForm()

    # Dynamically populate book choices
    books = Book.query.all()
    form.book_id.choices = [(0, 'Select a book...')] + [(book.id, book.title) for book in books]

    # Get recent feedback
    recent_feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).limit(10).all()

    if form.validate_on_submit():
        book_id = form.book_id.data if form.book_id.data != 0 else None
        rating_value = form.rating.data if form.rating.data != 0 else None

        # Create feedback
        new_feedback = Feedback(
            user_id=current_user.id,
            book_id=book_id,
            feedback_type=form.feedback_type.data,
            message=form.message.data,
            rating=rating_value,
            created_at=datetime.utcnow()
        )
        db.session.add(new_feedback)

        # If it's a book review with rating, also add to BookRating
        if book_id and rating_value and form.feedback_type.data == 'book_review':
            # Check if user already rated this book
            existing_rating = BookRating.query.filter_by(
                user_id=current_user.id, 
                book_id=book_id
            ).first()

            if existing_rating:
                existing_rating.rating = rating_value
                existing_rating.created_at = datetime.utcnow()
            else:
                new_rating = BookRating(
                    user_id=current_user.id,
                    book_id=book_id,
                    rating=rating_value,
                    created_at=datetime.utcnow()
                )
                db.session.add(new_rating)

        db.session.commit()
        flash("Thank you for your feedback!", "success")
        return redirect(url_for('feedback'))

    return render_template('feedback.html', username=current_user.username, form=form, recent_feedbacks=recent_feedbacks)

@app.route('/submit-feedback', methods=['POST'])
@login_required
def submit_feedback_api():
    """API endpoint for submitting feedback via AJAX"""
    if not request.is_json:
        return jsonify({"success": False, "message": "Invalid request format"}), 400

    data = request.json
    if not data.get("feedback"):
        return jsonify({"success": False, "message": "Feedback message is required"}), 400

    book_id = data.get("book_id")
    if book_id:
        try:
            book_id = int(book_id)
        except ValueError:
            book_id = None

    rating_value = data.get("rating")
    if rating_value:
        try:
            rating_value = int(rating_value)
            if rating_value < 1 or rating_value > 5:
                rating_value = None
        except ValueError:
            rating_value = None

    # Create feedback
    new_feedback = Feedback(
        user_id=current_user.id,
        book_id=book_id,
        feedback_type=data.get("feedback_type", "general"),
        message=data.get("feedback"),
        rating=rating_value,
        created_at=datetime.utcnow()
    )
    db.session.add(new_feedback)

    # If it's a book review with rating, also add to BookRating
    if book_id and rating_value and data.get("feedback_type") == 'book_review':
        # Check if user already rated this book
        existing_rating = BookRating.query.filter_by(
            user_id=current_user.id, 
            book_id=book_id
        ).first()

        if existing_rating:
            existing_rating.rating = rating_value
            existing_rating.created_at = datetime.utcnow()
        else:
            new_rating = BookRating(
                user_id=current_user.id,
                book_id=book_id,
                rating=rating_value,
                created_at=datetime.utcnow()
            )
            db.session.add(new_rating)

    db.session.commit()
    return jsonify({"success": True, "message": "Feedback submitted successfully!"})

@app.route('/get-recent-feedback')
@login_required
def get_recent_feedback():
    """API endpoint to get recent feedback in JSON format"""
    feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).limit(10).all()

    feedback_list = []
    for fb in feedbacks:
        user = User.query.get(fb.user_id)
        book_title = None
        if fb.book_id:
            book = Book.query.get(fb.book_id)
            if book:
                book_title = book.title

        feedback_data = {
            'id': fb.id,
            'username': user.username if user else "Anonymous",
            'type': fb.feedback_type,
            'message': fb.message,
            'rating': fb.rating,
            'book_title': book_title,
            'created_at': fb.created_at.strftime('%B %d, %Y')
        }
        feedback_list.append(feedback_data)

    return jsonify(feedback_list)

@app.route('/search', methods=['GET'])
@login_required
def search():
    query = request.args.get('query', '')
    if not query:
        return redirect(url_for('home'))

    # Search in book titles, authors, and descriptions
    books = Book.query.filter(
        db.or_(
            Book.title.ilike(f'%{query}%'),
            Book.author.ilike(f'%{query}%'),
            Book.description.ilike(f'%{query}%')
        )
    ).all()

    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)

    return render_template('search_results.html', 
                          username=current_user.username, 
                          books=books, 
                          query=query)
@app.route('/contact')
@login_required
def contact():
    return render_template('contact.html', username=current_user.username)

@app.route('/my-library', methods=['GET', 'POST'])
@login_required
def my_library():
    form = BookUploadForm()
    books = Book.query.filter_by(uploaded_by=current_user.id).all()

    if form.validate_on_submit():
        book_file = form.book.data
        filename = secure_filename(book_file.filename)  # Secure the filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Save the file to the uploads folder
        book_file.save(file_path)

        # Save book details to the database
        new_book = Book(
            title=form.book_name.data,
            author=form.author.data,
            category=form.category.data,
            description=form.description.data,
            image_url=form.image_url.data,  # Save the image URL
            filename=filename,
            file_path=file_path,
            uploaded_by=current_user.id
        )
        db.session.add(new_book)
        db.session.commit()
        flash("Book uploaded successfully!", "success")

        return redirect(url_for('my_library'))

    # For each book, get ratings
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)

    return render_template('my-library.html', username=current_user.username, uploaded_books=books, form=form)
@app.route('/book/<int:book_id>', endpoint='unique_book_details')
@login_required
def book_details(book_id):
    book = Book.query.get_or_404(book_id)
    # Get book ratings
    ratings = BookRating.query.filter_by(book_id=book_id).all()
    avg_rating = sum([r.rating for r in ratings]) / len(ratings) if ratings else 0
    # Get book reviews (feedback of type 'book_review')
    reviews = Feedback.query.filter_by(book_id=book_id, feedback_type='book_review').order_by(Feedback.created_at.desc()).all()
    
    # Check if current user has rated this book
    user_rating = BookRating.query.filter_by(book_id=book_id, user_id=current_user.id).first()
    
    return render_template('book_details.html', 
                          book=book, 
                          avg_rating=avg_rating, 
                          rating_count=len(ratings),
                          reviews=reviews,
                          user_rating=user_rating.rating if user_rating else None)

@app.route('/rate-book', methods=['POST'])
@login_required
def rate_book():
    book_id = request.form.get('book_id')
    rating = request.form.get('rating')
    
    if not book_id or not rating:
        flash("Book ID and rating are required", "danger")
        return redirect(request.referrer or url_for('home'))
    
    try:
        book_id = int(book_id)
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(request.referrer or url_for('home'))
    
    # Check if book exists
    book = Book.query.get(book_id)
    if not book:
        flash("Book not found", "danger")
        return redirect(request.referrer or url_for('home'))
    
    # Check if user has already rated this book
    existing_rating = BookRating.query.filter_by(
        user_id=current_user.id,
        book_id=book_id
    ).first()
    
    if existing_rating:
        # Update existing rating
        existing_rating.rating = rating
        existing_rating.created_at = datetime.utcnow()
        db.session.commit()
        flash("Your rating has been updated!", "success")
    else:
        # Create new rating
        new_rating = BookRating(
            user_id=current_user.id,
            book_id=book_id,
            rating=rating
        )
        db.session.add(new_rating)
        db.session.commit()
        flash("Thank you for rating this book!", "success")
    
    # Redirect back to the book details page
    return redirect(url_for('book_details', book_id=book_id))

@app.route('/get-ratings/<int:book_id>')
def get_ratings(book_id):
    book = Book.query.get_or_404(book_id)
    ratings = BookRating.query.filter_by(book_id=book_id).all()
    
    rating_data = {
        'average': book.average_rating,
        'count': len(ratings),
        'distribution': {
            '5': BookRating.query.filter_by(book_id=book_id, rating=5).count(),
            '4': BookRating.query.filter_by(book_id=book_id, rating=4).count(),
            '3': BookRating.query.filter_by(book_id=book_id, rating=3).count(),
            '2': BookRating.query.filter_by(book_id=book_id, rating=2).count(),
            '1': BookRating.query.filter_by(book_id=book_id, rating=1).count()
        }
    }
    
    return jsonify(rating_data)

@app.route('/fantasy')
@login_required
def fantasy():
    books = Book.query.filter_by(category="Fantasy").all()  # Corrected to use consistent capitalization
    
    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)
        
    return render_template('fantasy.html', username=current_user.username, books=books)

@app.route('/science')
@login_required
def science():
    books = Book.query.filter_by(category="Science").all()
    
    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)
        
    return render_template('science.html', username=current_user.username, books=books)

@app.route('/biographies')
@login_required
def biographies():
    books = Book.query.filter_by(category="biographies").all()
    
    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)
        
    return render_template('biographies.html', username=current_user.username, books=books)

@app.route('/technology')
@login_required
def technology():
    books = Book.query.filter_by(category="technology").all()
    
    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)
        
    return render_template('technology.html', username=current_user.username, books=books)

@app.route('/astronomy')
@login_required
def astronomy():
    books = Book.query.filter_by(category="astronomy").all()

    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)

    return render_template('astronomy.html', username=current_user.username, books=books)

@app.route('/comics')
@login_required
def comics():
    books = Book.query.filter_by(category="comics").all()
    
    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)
        
    return render_template('comics.html', username=current_user.username, books=books)

@app.route('/fiction')
@login_required
def fiction():
    books = Book.query.filter_by(category="Fiction").all()  # Corrected to use consistent capitalization
    
    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)
        
    return render_template('fiction.html', username=current_user.username, books=books)


@app.route('/history')
@login_required
def history():
    books = Book.query.filter_by(category="history").all()  # Corrected to use consistent capitalization
    
    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)
        
    return render_template('history.html', username=current_user.username, books=books)

@app.route('/mystery')
@login_required
def mystery():
    books = Book.query.filter_by(category="mystery").all()
    
    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)
        
    return render_template('mystery.html', username=current_user.username, books=books)

@app.route('/medical science')
@login_required
def medicalscience():
    books = Book.query.filter_by(category="medical science").all()
    
    # Add rating information for each book
    for book in books:
        book.avg_rating = book.average_rating
        book.rating_count = len(book.ratings)
        
    return render_template('medical science.html', username=current_user.username, books=books)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out successfully!", "success")
    return redirect(url_for('login'))

@app.route('/science-books', methods=['GET'])
def get_science_books():
    science_books = Book.query.filter_by(category="Science").all()
    
    books_list = [
        {
            "title": book.title,
            "author": book.author,
            "image": book.image_url if hasattr(book, 'image_url') else None,
            "file": book.file_path,
            "rating": round(book.average_rating, 1) if book.ratings else 0,
            "rating_count": len(book.ratings)
        }
        for book in science_books
    ]

    return jsonify(books_list)

@app.route('/edit-book', methods=['POST'])
@login_required
def edit_book():
    book_id = request.form.get('book_id')
    book = Book.query.get(book_id)
    
    # Check if book exists and belongs to current user
    if not book or book.uploaded_by != current_user.id:
        flash("Book not found or you don't have permission to edit it.", "danger")
        return redirect(url_for('my_library'))
    
    # Update book details
    book.title = request.form.get('book_name')
    book.author = request.form.get('author')
    book.category = request.form.get('category')
    book.description = request.form.get('description')
    book.image_url = request.form.get('image_url')  # Update the image URL
    
    db.session.commit()
    flash("Book details updated successfully!", "success")
    return redirect(url_for('my_library'))

@app.route('/book/<int:book_id>')
@login_required
def book_details(book_id):
    book = Book.query.get_or_404(book_id)
    # Get book ratings
    ratings = BookRating.query.filter_by(book_id=book_id).all()
    avg_rating = sum([r.rating for r in ratings]) / len(ratings) if ratings else 0
    # Get book reviews (feedback of type 'book_review')
    reviews = Feedback.query.filter_by(book_id=book_id, feedback_type='book_review').order_by(Feedback.created_at.desc()).all()
    
    # Check if current user has rated this book
    user_rating = BookRating.query.filter_by(book_id=book_id, user_id=current_user.id).first()
    
    return render_template('book_details.html', 
                          book=book, 
                          avg_rating=avg_rating, 
                          rating_count=len(ratings),
                          reviews=reviews,
                          user_rating=user_rating.rating if user_rating else None)


@app.route('/delete-book', methods=['POST'])
@login_required
def delete_book():
    book_id = request.form.get('book_id')
    book = Book.query.get(book_id)
    
    # Check if book exists and belongs to current user
    if not book or book.uploaded_by != current_user.id:
        flash("Book not found or you don't have permission to delete it.", "danger")
        return redirect(url_for('my_library'))
    
    # Get the file path
    file_path = book.file_path
    
    # Delete associated ratings
    BookRating.query.filter_by(book_id=book.id).delete()
    
    # Delete associated feedback
    Feedback.query.filter_by(book_id=book.id).delete()
    
    # Delete from database
    db.session.delete(book)
    db.session.commit()
    
    # Delete the file if it exists
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except:
            # Log error but continue if file deletion fails
            print(f"Could not delete file: {file_path}")
    
    flash("Book deleted successfully!", "success")
    return redirect(url_for('my_library'))

@app.route('/category/<category_name>')
def get_books(category_name):
    books = Book.query.filter_by(category=category_name).all()

    if not books:
        return jsonify([])  # Return an empty list if no books are found

    books_data = [
        {
            "id": book.id,
            "title": book.title,
            "author": book.author,
            "filename": book.filename,
            "image_url": book.image_url if hasattr(book, 'image_url') else None,  # Safely access image_url
            "avg_rating": round(book.average_rating, 1) if book.ratings else 0,
            "rating_count": len(book.ratings)
        }
        for book in books
    ]
    return jsonify(books_data)

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form.get('username')
        
        # Find the user
        user = User.query.filter_by(username=username).first()
        
        if not user:
            flash("No account found with that username.", "danger")
            return redirect(url_for('reset_password'))
            
        # Check security question and answer (you'll need to add these fields to your User model)
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for('reset_password'))
            
        # Update the password
        hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        user.password_hash = hashed_password
        db.session.commit()
        
        flash("Password has been reset successfully. Please login with your new password.", "success")
        return redirect(url_for('login'))
        
    return render_template('reset_password.html')

@app.route('/download/<int:book_id>')
def download_book(book_id):
    book = Book.query.get(book_id)

    if not book:
        return abort(404, description="Book not found")

    # Use the app configuration for UPLOAD_FOLDER
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], book.filename)

    if not os.path.exists(file_path):
        return abort(404, description="File not found")

    return send_from_directory(app.config['UPLOAD_FOLDER'], book.filename, as_attachment=True)

# Database migration function to add the missing columns
def migrate_database():
    with app.app_context():
        # Check if the columns exist
        import sqlite3
        try:
            conn = sqlite3.connect('instance/users.db')
            cursor = conn.cursor()
            
            # Check book table columns
            cursor.execute('PRAGMA table_info(book)')
            book_columns = [column[1] for column in cursor.fetchall()]
            
            # If image_url column doesn't exist, add it
            if 'image_url' not in book_columns:
                cursor
                conn.commit()
                print("Added image_url column to book table")
            
            # Check if BookRating table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='book_rating'")
            if not cursor.fetchone():
                # Create BookRating table
                cursor.execute('''
                CREATE TABLE book_rating (
                    id INTEGER PRIMARY KEY,
                    book_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL,
                    created_at TIMESTAMP,
                    FOREIGN KEY (book_id) REFERENCES book (id),
                    FOREIGN KEY (user_id) REFERENCES user (id),
                    UNIQUE (book_id, user_id)
                )
                ''')
                conn.commit()
                print("Created BookRating table")
            
            # Check if Feedback table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
            if not cursor.fetchone():
                # Create Feedback table
                cursor.execute('''
                CREATE TABLE feedback (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    book_id INTEGER,
                    feedback_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    rating INTEGER,
                    created_at TIMESTAMP,
                    FOREIGN KEY (book_id) REFERENCES book (id),
                    FOREIGN KEY (user_id) REFERENCES user (id)
                )
                ''')
                conn.commit()
                print("Created Feedback table")
            
            conn.close()
        except Exception as e:
            print(f"Migration error: {e}")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create tables if they don't exist
        migrate_database()  # Add the missing columns/tables
    app.run(debug=True)