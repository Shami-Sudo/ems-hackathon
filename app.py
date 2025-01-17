import csv
from flask import Flask, render_template, request, flash, send_file, session, redirect, url_for
from hashlib import sha256
import pymongo
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename
from PIL import Image
from pytesseract import pytesseract
import datefinder
import os
import re
from datetime import datetime, date

from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, SubmitField, FieldList, FormField
from wtforms.validators import DataRequired, Email, NumberRange, Optional
from helper import allowed_file, convert, send_email_notification, date_validator

from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()


app.config['SECRET_KEY'] = os.environ['SECRET_KEY_STR']
app.config['UPLOAD_FOLDER'] = 'static/images/uploaded'
uri = os.environ['DB_CONNECT']


client = pymongo.MongoClient(uri)


db = client.avalanche


events_db = db.events
users_db = db.users
brochures_db = db.brochures
registrations_db = db.registrations


def image_to_text(path_im):
    path_to_tesseract = r"C:/Program Files/Tesseract-OCR/tesseract.exe"
    image_path = path_im
    pytesseract.tesseract_cmd = path_to_tesseract
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img)
    ocr_text = text

    venue_pattern = r'\b(?:[A-Z][a-z]*\s)*[A-Z][a-z]*\s(?:[A-Z][a-z]*\s)*\b(?:Auditorium|Classroom|Hotel|Floor|Venue)\b'
    venues = re.findall(venue_pattern, ocr_text)
    if len(venues) > 0:
        venues = venues[0]
    else:
        venues = ''

    matches = datefinder.find_dates(ocr_text)
    ns = []
    for match in matches:
        s = str(match.date())
        if s[8:] in ocr_text:
            ns.append(s)
    if len(ns) > 0:
        dates = ns[-1]
    else:
        dates = ''

    time_pattern = r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b'
    times = re.findall(time_pattern, ocr_text)
    if len(times) > 0:
        # for i in times:
        times = convert(times[0]).rstrip()
        # print(times)
    else:
        times = datetime.strptime('10:00 am', '%I:%M %p').time()
        times = times.strftime("%I:%M")
        print(times)

    return venues, dates, times


class IndividualRegistrationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    reg_number = StringField('Registration Number',
                             validators=[DataRequired()])
    mobile_number = StringField('Mobile Number', validators=[DataRequired()])
    branch = SelectField('Branch', choices=[('CSE', 'CSE'), ('IT', 'IT'), ('EEE', 'EEE'), ('ECE', 'ECE'), ('Mechanical', 'Mechanical'), (
        'Mechatronics', 'Mechatronics'), ('Bio Informatics', 'Bio Informatics')], validators=[DataRequired()])
    section = StringField('Section', validators=[DataRequired()])
    year = SelectField('Year', choices=[('1', '1st Year'), ('2', '2nd Year'), (
        '3', '3rd Year'), ('4', '4th Year')], validators=[DataRequired()])
    submit = SubmitField('Register')


@app.route('/home', methods=['GET'])
def events():
    print(session.items())
    if 'is_admin' in session:
        is_admin = session['is_admin']
    else:
        is_admin = False
    today_date = str(date.today())
    event = events_db.find()
    return render_template('events.html', event=event, today_date=today_date, is_admin=is_admin)


admin_username = os.environ['ADMIN_USERNAME']
admin_password = os.environ['ADMIN_PASS']
admin_hashpass = sha256(str(admin_password).encode()).hexdigest()

# @app.errorhandler(Exception)
# def handle_error(error):
#     return render_template('errorhandler.html'), 500


@app.route('/', methods=['GET', "POST"])
@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        # print(username, password)
        hashed_password = sha256(str(password).encode()).hexdigest()

        user = users_db.find_one(
            {'username': username}
        )
        # print(user)

        if username == admin_username:
            if hashed_password == admin_hashpass:
                session['is_admin'] = True
                flash("Logged in Successfully")
                return redirect(url_for('events'))
            else:
                flash("Incorrect Password")
        else:
            if user:
                if hashed_password == user['password']:
                    session['is_admin'] = False
                    session['username'] = username
                    flash("Logged in Successfully")
                    return redirect(url_for('events'))
                else:
                    flash("Incorrect Password")
            else:
                flash("User doesnt exist")
                return redirect('/register')

    return render_template('userlogin.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        cpassword = request.form.get('cpassword')
        user = users_db.find_one(
            {'username': username}
        )
        if user == None:
            if password == cpassword:
                hashpass = sha256(str(password).encode()).hexdigest()
                users_db.insert_one(
                    {'username': username, 'password': hashpass})
                # session['is_admin'] = False
                flash("Registration successful. Go ahead and login")
                return redirect('/login')
            else:
                flash('passwords donot match')
        else:
            flash('Username already exists.Kindly Login')
            return redirect('/login')
    return render_template('userregister.html')


@app.route("/logout", methods=["POST", "GET"])
def logout():
    if session['is_admin'] == True:
        session.pop("is_admin", None)
        flash("You are now logged out")
        return redirect('/home')
    elif session['is_admin'] == False and session['username']:
        session.pop("username", None)
        session.pop("is_admin", None)

        flash("please Dont go,come back :(")
        return redirect('/home')
    else:
        return redirect('/home')


@app.route("/addevent", methods=["POST", "GET"])
def addevent():
    print(session, '===================')
    if session['is_admin'] == True:

        if request.method == 'POST':
            if 'uploaded_file' not in request.files:
                flash("No file is uploaded")
            brochure = request.files['uploaded_file']
            if brochure.filename == '':
                flash("No img selected")
            if brochure and allowed_file(brochure.filename):
                brochure.save(os.path.join(os.path.abspath(os.path.dirname(
                    __file__)), app.config['UPLOAD_FOLDER'], secure_filename(brochure.filename)))
                brochures_db.insert_one(
                    {
                        'uploaded_brochure': f'static/images/uploaded/{secure_filename(brochure.filename)}'
                    }
                )
                venue_event = image_to_text(
                    f'static/images/uploaded/{secure_filename(brochure.filename)}')[0]
                date_event = image_to_text(
                    f'static/images/uploaded/{secure_filename(brochure.filename)}')[1]
                time_event = image_to_text(
                    f'static/images/uploaded/{secure_filename(brochure.filename)}')[2]
                show = True
                return render_template('addevent.html', poster=f'static/images/uploaded/{secure_filename(brochure.filename)}', venue=venue_event, date=date_event, time=time_event, show=show)

        return render_template('addevent.html')
    else:
        return redirect('/userlogin')


@app.route('/upload', methods=["POST"])
def upload():
    event_name = request.form.get('event_name')
    event_date = request.form.get('event_date')
    event_time = request.form.get('event_time')
    event_venue = request.form.get('event_venue')
    event_eligibility = request.form.get('event_eligibility')
    event_awards = request.form.get('event_awards')
    event_desc = request.form.get('event_desc')
    event_deadline = request.form.get('event_deadline')
    event_limit = request.form.get('event_limit')
    dept = request.form.get('dept')
    event_type = request.form.get('type')
    # print(dept)
    event_cord = request.form.get('event_cord')
    broc = brochures_db.find().sort('_id', pymongo.DESCENDING).limit(1)
    for i in broc:
        file_path = i['uploaded_brochure']
    if date_validator(event_date, event_deadline) == False:
        flash("Registration Deadline should be on or before the event date")
        return render_template('addevent.html')

    else:
        events_db.insert_one(
            {
                'poster': file_path,
                'name': event_name,
                'venue': event_venue,
                'date': event_date,
                'time': event_time,
                'awards': event_awards,
                'eligibility': event_eligibility,
                'desc': event_desc,
                'deadline': event_deadline,
                'rlimit': event_limit,
                'dept': dept,
                'contact': event_cord,
                'type': event_type,
                'reg_count': 0


            }
        )
        flash('Event added successfully!')

        return redirect('/home')


@app.route('/<id>/edit', methods=['GET', 'POST'])
def edit_event(id):
    event = events_db.find_one({"_id": ObjectId(id)})
    return render_template('modify.html', id=id, event=event)


@app.route('/update_event/<id>', methods=['GET', 'POST'])
def update_event(id):
    event = events_db.find_one({"_id": ObjectId(id)})
    event_name = request.form.get('event_name')
    event_date = request.form.get('event_date')
    event_time = request.form.get('event_time')
    event_venue = request.form.get('event_venue')
    event_eligibility = request.form.get('event_eligibility')
    event_awards = request.form.get('event_awards')
    event_desc = request.form.get('event_desc')
    event_deadline = request.form.get('event_deadline')
    event_limit = request.form.get('event_limit')
    dept = request.form.get('dept')
    event_cord = request.form.get('event_cord')
    event_type = request.form.get('type')
    if date_validator(event_date, event_deadline) == False:
        flash("Registration Deadline should be on or before the event date")
        return render_template('modify.html', id=id, event=event)
    else:
        events_db.update_one({"_id": ObjectId(id)},
                             {"$set": {
                                 'name': event_name,
                                 'venue': event_venue,
                                 'date': event_date,
                                 'time': event_time,
                                 'awards': event_awards,
                                 'eligibility': event_eligibility,
                                 'desc': event_desc,
                                 'deadline': event_deadline,
                                 'rlimit': event_limit,
                                 'dept': dept,
                                 'contact': event_cord,
                                 'type': event_type
                             }}
                             )
        # print(events_db.find_one({"_id": ObjectId(id)}))
        flash('Event updated successfully!')
        return redirect('/home')


@app.route('/delete/<id>', methods=['GET', 'POST'])
def delete(id):
    # print(id)
    events_db.delete_one({"_id": ObjectId(id)})
    flash('Event Deleted successfully!')
    return redirect('/home')


@app.route('/export/<id>', methods=['GET'])
def export(id):
    records = registrations_db.find({"event_id": id})
    event = events_db.find_one({"_id": ObjectId(id)})
    # print(records, '-----------------------------')
    if registrations_db.count_documents({"event_id": id}) == 0:
        flash("No records found for the event.")
        return redirect('/home')
    csv_file = f"{event['name']}.csv"
    with open(csv_file, 'w', newline="") as reg_file:
        writer_obj = csv.DictWriter(reg_file, fieldnames=records[0].keys())
        writer_obj.writeheader()
        writer_obj.writerows(records)
    return send_file(csv_file, as_attachment=True)


@app.route('/register/<id>', methods=['GET', 'POST'])
def event_register(id):
    if 'is_admin' in session and session['is_admin'] == False:
        username = session['username']
        event = events_db.find_one({"_id": ObjectId(id)})
        form = IndividualRegistrationForm()
        registration_count = registrations_db.count_documents({'event_id': id})
        events_db.update_one({"_id": ObjectId(id)},
                             {"$set": {"reg_count": registration_count}})
        # print(registration_count, 'brrrrrrrrrrrr')

        registration_limit = int(event['rlimit'])

        # print(registration_limit, 'hhhhhhhhhhhhh', type(
        # registration_limit), type(registration_count))

        if registration_count >= registration_limit:
            flash('Registration limit has been reached for this event.')
            return redirect('/home')

        elif form.validate_on_submit():
            reg_num = form.reg_number.data
            email = form.email.data

            existing_registration = registrations_db.find_one({
                'event_id': id,
                "$or": [{'email': email}, {'reg_num': reg_num}],

            })
            # print(existing_registration)
            if existing_registration:
                flash('You have already registered for this event.')
                return redirect('/home')

            registration_data = {
                'name': form.name.data,
                'email': email,
                'reg_num': reg_num,
                'mobile_num': form.mobile_number.data,
                'branch': form.branch.data,
                'section': form.section.data,
                'year': form.year.data,
                'event_id': id,
                "event_name": event['name']
            }
            # print(registration_data)
            registrations_db.insert_one(registration_data)
            send_email_notification(registration_data, event)
            flash('Registration successful.Confirmation Mail sent :)')
            return redirect('/home')
        return render_template('indreg.html', form=form, event=event, registration_count=registration_count, username=username)
    elif 'is_admin' not in session:
        flash('Login to register :)')
        return redirect('\login')


@app.route('/categories')
def categories():
    print(request.args)
    department = request.args.get('department')
    event_name = request.args.get('name')
    month = request.args.get('month')
    event_type = request.args.get('type')
    filters = {}
    if department:
        filters['dept'] = department
    if event_name:
        filters['name'] = {'$regex': event_name, '$options': 'i'}
    if month:
        if int(month) < 10:
            filters['date'] = {'$regex': f'0{month}-'}
        else:
            filters['date'] = {'$regex': f'{month}-'}
    if event_type:
        filters['type'] = event_type
    # print(f"FLTER: {filters}")
    filtered_events = list(events_db.find(filters))

    return render_template('categories.html', filtered_events=filtered_events)


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")


# class TeamMemberForm(FlaskForm):
#     reg_number = StringField('Registration Number')


# class TeamRegistrationForm(FlaskForm):
#     team_lead_name = StringField('Team Leader Name', validators=[DataRequired()])
#     team_lead_email = StringField('Team Leader Email', validators=[DataRequired(), Email()])
#     team_lead_branch = SelectField('Team Leader Branch', choices=[('CSE', 'CSE'), ('IT', 'IT'), ('EEE', 'EEE'),('ECE','ECE'),('Mechanical','Mechanical'),('Mechatronics','Mechatronics'),('Bio Informatics','Bio Informatics')], validators=[DataRequired()])
#     team_lead_year = SelectField('Team Leader Year', choices=[('1st', '1st Year'), ('2nd', '2nd Year'), ('3rd', '3rd Year'),('4th','4th year')], validators=[DataRequired()])
#     team_lead_section = StringField('Team Leader Section', validators=[DataRequired()])
#     team_lead_reg_num = StringField('Team Leader Registration Number', validators=[DataRequired()])
#     team_size = StringField('Team Size', validators=[DataRequired()])
#     team_members = FieldList(FormField(TeamMemberForm), min_entries=2, max_entries=10)
#     submit = SubmitField('Register')


# @app.route('/register/<id>', methods=['GET', 'POST'])
# def event_register(id):
#     event = events_db.find_one({"_id": ObjectId(id)})
#     event_size = 4
#     print(event)
#     event_type = event['type']

#     if event_type == 'individual':
#         form = IndividualRegistrationForm()
#         if form.validate_on_submit():
#             registration_data = {
#                 'Name': form.name.data,
#                 'Email': form.email.data,
#                 'Registration Number': form.reg_number.data,
#                 'Mobile Number': form.mobile_number.data,
#                 'Branch': form.branch.data,
#                 'Section': form.section.data,
#                 'Year': form.year.data
#             }
#             print(registration_data)
#             save_team_registration_data(registration_data,event['name'])
#             # send_email_notification(registration_data,event)
#             flash('Registration successful!')
#             return redirect('/home')
#         return render_template('indreg.html',form=form,event=event)
#     elif event_type == 'team':
#         print('--------------------------------------------------------hi')
#         form = TeamRegistrationForm()
#         form.team_members.entries = [TeamMemberForm() for _ in range(event_size - 1)]
#         if form.validate_on_submit():
#             print('---------------------')
#             registration_data = {
#                 'Team Lead Name': form.team_lead_name.data,
#                 'Team Lead Email': form.team_lead_email.data,
#                 'Team Lead Branch': form.team_lead_branch.data,
#                 'Team Lead Year': form.team_lead_year.data,
#                 'Team Lead Section': form.team_lead_section.data,
#                 'Team Lead Registration Number': form.team_lead_reg_num.data,
#                 'Team Size': form.team_size.data,
#                 'Team Member Registration Numbers': [field.reg_number.data for field in form.team_members]
#             }
#             print(registration_data)

#             save_team_registration_data(registration_data,event['name'])
#             # send_email_notification(registration_data,event)
#             flash('Registration successful!')
#             return redirect('/home')
#         else:
#             print(form.errors)
#         return render_template('teamreg.html',form=form,event=event)
