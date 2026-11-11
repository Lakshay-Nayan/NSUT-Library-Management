from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import re

from flask import Flask, render_template, request, redirect, url_for, flash
from database import get_connection, initialize_database

app = Flask(__name__)
app.secret_key = "change-this-to-a-long-random-secret"

LOAN_DAYS = 14
MAX_BOOKS_PER_STUDENT = 3
LATE_FINE_PER_DAY = Decimal("5.00")



def parse_roll_number(roll_no):
    roll_no = roll_no.strip().upper()

    match = re.fullmatch(
        r"(202[3-6])U([A-Z]{2})(\d{4})",
        roll_no
    )

    if not match:
        raise ValueError(
            "Invalid roll number. Expected format: "
            "2026UXX1234. Enrollment year must be 2023-2026."
        )

    enrollment_year, _, class_roll = match.groups()

    enrollment_year = int(enrollment_year)

    return {
        "enrollment_year": enrollment_year,
        "student_type": "Undergraduate",
        "study_year": date.today().year - enrollment_year + 1,
        "series_code": "",
        "class_roll": class_roll
    }


def query_all(sql, values=()):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(sql, values)
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return rows


def execute_query(sql, values=()):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(sql, values)
    connection.commit()
    last_id = cursor.lastrowid
    cursor.close()
    connection.close()
    return last_id


@app.route("/")
def index():
    stats = query_all("""
        SELECT
            (SELECT COUNT(*) FROM books) AS book_titles,
            (SELECT COALESCE(SUM(total_copies), 0) FROM books) AS total_copies,
            (SELECT COALESCE(SUM(available_copies), 0) FROM books) AS available_copies,
            (SELECT COUNT(*) FROM students) AS students,
            (SELECT COUNT(*) FROM issues WHERE status = 'Issued') AS issued,
            (SELECT COUNT(*) FROM issues
             WHERE status = 'Issued' AND due_date < CURDATE()) AS overdue
    """)[0]

    recent = query_all("""
        SELECT issues.id, books.title, students.name, students.roll_no,
               issues.issue_date, issues.due_date, issues.status
        FROM issues
        JOIN books ON issues.book_id = books.id
        JOIN students ON issues.student_id = students.id
        ORDER BY issues.id DESC LIMIT 8
    """)
    return render_template("index.html", stats=stats, recent=recent)



@app.route("/books")
def books():
    search = request.args.get("q", "").strip()

    rows = query_all("""
        SELECT *,
        (total_copies - available_copies) AS issued_copies
        FROM books
        WHERE title LIKE %s
        OR author LIKE %s
        OR isbn LIKE %s
        ORDER BY title
    """, (f"%{search}%", f"%{search}%", f"%{search}%"))

    return render_template(
        "books.html",
        books=rows,
        search=search
    )



@app.route("/books/add", methods=["GET", "POST"])
def add_book():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        isbn = request.form.get("isbn", "").strip() or None
        category = request.form.get("category", "").strip()
        price = request.form.get("price", "0").strip()
        copies = request.form.get("copies", "1").strip()

        try:
            price_value = Decimal(price)
            copies_value = int(copies)
            if not title or not author or price_value < 0 or copies_value < 1:
                raise ValueError
            execute_query("""
                INSERT INTO books
                (title, author, isbn, category, total_copies, available_copies, price)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (title, author, isbn, category, copies_value, copies_value, price_value))
            flash("Book added successfully.", "success")
            return redirect(url_for("books"))
        except (ValueError, InvalidOperation):
            flash("Please enter valid book details, price and copy count.", "error")
        except Exception as error:
            flash(f"Could not add book. Check whether the ISBN already exists. ({error})", "error")

    return render_template("add_book.html")



@app.route("/students")
def students():
    search = request.args.get("q", "").strip()

    rows = query_all("""
        SELECT * FROM students
        WHERE name LIKE %s OR roll_no LIKE %s
        ORDER BY roll_no
    """, (f"%{search}%", f"%{search}%"))

    return render_template("students.html", students=rows, search=search)


@app.route("/students/register", methods=["GET", "POST"])
def register_student():
    parsed = None
    if request.method == "POST":
        roll_no = request.form.get("roll_no", "").strip().upper()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()

        try:
            parsed = parse_roll_number(roll_no)
            if not name:
                raise ValueError("Student name is required.")

            execute_query("""
                INSERT INTO students
                (roll_no, name, email, phone, enrollment_year, student_type,
                 study_year, series_code, class_roll)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                roll_no, name, email, phone,
                parsed["enrollment_year"], parsed["student_type"],
                parsed["study_year"], parsed["series_code"], parsed["class_roll"]
            ))
            flash("Student registered successfully.", "success")
            return redirect(url_for("students"))
        except ValueError as error:
            flash(str(error), "error")
        except Exception as error:
            flash(f"Could not register student. Roll number may already exist. ({error})", "error")

    return render_template("register_student.html")


@app.route("/issue", methods=["GET", "POST"])
def issue_book():
    if request.method == "POST":
        book_id = request.form.get("book_id")
        student_id = request.form.get("student_id")
        issue_date = date.today()
        due_date = issue_date + timedelta(days=LOAN_DAYS)

        try:
            book = query_all("SELECT * FROM books WHERE id = %s", (book_id,))
            student = query_all("SELECT * FROM students WHERE id = %s", (student_id,))
            if not book or not student:
                raise ValueError("Select a valid book and student.")
            if book[0]["available_copies"] < 1:
                raise ValueError("No copies of this book are currently available.")

            active = query_all("""
                SELECT COUNT(*) AS total FROM issues
                WHERE student_id = %s AND status = 'Issued'
            """, (student_id,))[0]["total"]
            if active >= MAX_BOOKS_PER_STUDENT:
                raise ValueError(f"This student already has {MAX_BOOKS_PER_STUDENT} books issued.")

            connection = get_connection()
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO issues (book_id, student_id, issue_date, due_date, status)
                VALUES (%s, %s, %s, %s, 'Issued')
            """, (book_id, student_id, issue_date, due_date))
            cursor.execute("""
                UPDATE books SET available_copies = available_copies - 1
                WHERE id = %s AND available_copies > 0
            """, (book_id,))
            if cursor.rowcount != 1:
                connection.rollback()
                raise ValueError("Book availability changed. Please try again.")
            connection.commit()
            cursor.close()
            connection.close()

            flash(f"Book issued. Return it by {due_date}.", "success")
            return redirect(url_for("issued_books"))
        except ValueError as error:
            flash(str(error), "error")
        except Exception as error:
            flash(f"Could not issue book: {error}", "error")

    books_list = query_all("SELECT * FROM books WHERE available_copies > 0 ORDER BY title")
    students_list = query_all("SELECT * FROM students ORDER BY roll_no")
    return render_template("issue_book.html", books=books_list, students=students_list,
                           loan_days=LOAN_DAYS, max_books=MAX_BOOKS_PER_STUDENT)


@app.route("/issued")
def issued_books():
    rows = query_all("""
        SELECT issues.*, books.title, students.name, students.roll_no,
               CASE WHEN issues.due_date < CURDATE() AND issues.status = 'Issued'
                    THEN DATEDIFF(CURDATE(), issues.due_date) ELSE 0 END AS overdue_days
        FROM issues
        JOIN books ON issues.book_id = books.id
        JOIN students ON issues.student_id = students.id
        ORDER BY issues.id DESC
    """)
    return render_template("issued_books.html", issues=rows)


@app.route("/return/<int:issue_id>", methods=["GET", "POST"])
def return_book(issue_id):
    issue = query_all("""
        SELECT issues.*, books.title, students.name, students.roll_no, students.id AS student_id
        FROM issues
        JOIN books ON issues.book_id = books.id
        JOIN students ON issues.student_id = students.id
        WHERE issues.id = %s
    """, (issue_id,))

    if not issue:
        flash("Issue record not found.", "error")
        return redirect(url_for("issued_books"))

    issue = issue[0]
    if issue["status"] != "Issued":
        flash("This book has already been returned.", "error")
        return redirect(url_for("issued_books"))

    if request.method == "POST":
        returned_on = date.today()
        overdue_days = max(0, (returned_on - issue["due_date"]).days)
        late_charge = LATE_FINE_PER_DAY * overdue_days
        damage_description = request.form.get("damage_description", "").strip()
        damage_charge_text = request.form.get("damage_charge", "0").strip()

        try:
            damage_charge = Decimal(damage_charge_text)
            if damage_charge < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            flash("Enter a valid non-negative damage charge.", "error")
            return render_template("return_book.html", issue=issue, overdue_days=overdue_days,
                                   late_charge=late_charge)

        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE issues SET return_date = %s, status = 'Returned' WHERE id = %s
        """, (returned_on, issue_id))
        cursor.execute("""
            UPDATE books SET available_copies = available_copies + 1 WHERE id = %s
        """, (issue["book_id"],))

        if late_charge > 0:
            cursor.execute("""
                INSERT INTO fines (issue_id, student_id, amount, reason)
                VALUES (%s, %s, %s, %s)
            """, (issue_id, issue["student_id"], late_charge,
                  f"Late return: {overdue_days} day(s)"))

        if damage_description and damage_charge > 0:
            cursor.execute("""
                INSERT INTO damages (issue_id, description, charge)
                VALUES (%s, %s, %s)
            """, (issue_id, damage_description, damage_charge))
            cursor.execute("""
                INSERT INTO fines (issue_id, student_id, amount, reason)
                VALUES (%s, %s, %s, %s)
            """, (issue_id, issue["student_id"], damage_charge, "Book damage"))

        connection.commit()
        cursor.close()
        connection.close()

        total_charge = late_charge + damage_charge
        flash(f"Book returned. Total new charge: ₹{total_charge:.2f}", "success")
        return redirect(url_for("issued_books"))

    overdue_days = max(0, (date.today() - issue["due_date"]).days)
    late_charge = LATE_FINE_PER_DAY * overdue_days
    return render_template("return_book.html", issue=issue, overdue_days=overdue_days,
                           late_charge=late_charge)


@app.route("/damages")
def damages():
    rows = query_all("""
        SELECT damages.*, books.title, students.name, students.roll_no
        FROM damages
        JOIN issues ON damages.issue_id = issues.id
        JOIN books ON issues.book_id = books.id
        JOIN students ON issues.student_id = students.id
        ORDER BY damages.id DESC
    """)
    return render_template("damages.html", damages=rows)


@app.route("/fines")
def fines():
    rows = query_all("""
        SELECT fines.*, students.name, students.roll_no, books.title
        FROM fines
        JOIN students ON fines.student_id = students.id
        JOIN issues ON fines.issue_id = issues.id
        JOIN books ON issues.book_id = books.id
        ORDER BY fines.id DESC
    """)
    return render_template("fines.html", fines=rows)


@app.route("/fines/pay/<int:fine_id>", methods=["POST"])
def pay_fine(fine_id):
    execute_query("UPDATE fines SET paid = TRUE WHERE id = %s", (fine_id,))
    flash("Fine marked as paid.", "success")
    return redirect(url_for("fines"))


if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)
