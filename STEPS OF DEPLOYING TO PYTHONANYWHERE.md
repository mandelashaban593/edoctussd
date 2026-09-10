our Django project is a good fit for a standard PythonAnywhere WSGI deployment. Because you want:

Django
GitHub as the source repository
PythonAnywhere hosting
custom domain edoctorug.com
HTTPS
your existing settings.py
USSD/IPN endpoints

I recommend deploying it as:

GitHub → PythonAnywhere Bash → virtualenv → Django WSGI → PythonAnywhere Web app → www.edoctorug.com → HTTPS

One important point first: PythonAnywhere recommends using a CNAME for www.edoctorug.com; the bare/apex edoctorug.com cannot normally be a CNAME. You can redirect the bare domain to www, depending on your DNS provider.

1. Your final deployment structure

I am assuming your GitHub repository looks approximately like this:

your-repository/
│
├── manage.py
├── requirements.txt
├── .gitignore
│
├── edoctussd/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── ...
│
├── dashboard/
│   ├── migrations/
│   ├── templates/
│   ├── static/
│   └── ...
│
├── templates/
│
└── db.sqlite3

The important thing is that:

manage.py

must be at the project root that you clone on PythonAnywhere.

2. Before deploying: prepare the GitHub repository
2.1 Create requirements.txt

On your development computer, activate your Django environment and run:

pip freeze > requirements.txt

At minimum, based on your settings.py, your requirements need packages corresponding to:

Django
djangorestframework
django-filter
python-decouple
whitenoise

If your project uses other packages—such as requests, psycopg, Pillow, gunicorn, etc.—they also need to be in requirements.txt.

I recommend checking:

cat requirements.txt

before pushing it.

3. Create a proper .gitignore

Do not push production secrets to GitHub.

Create:

.gitignore

with something like:

# Python
__pycache__/
*.py[cod]
*.pyo

# Virtual environments
venv/
.venv/
env/

# Django
*.log
db.sqlite3
staticfiles/

# Environment/secrets
.env

# IDE
.vscode/
.idea/

# OS
.DS_Store

Most importantly:

.env

should not go into GitHub.

4. Your .env file

Your current settings already use python-decouple:

SECRET_KEY = config("SECRET_KEY", default="dev-only-change-me")
DEBUG = config("DEBUG", default=True)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="127.0.0.1,localhost", cast=Csv())

That's good.

For production, create a .env locally that looks like:

SECRET_KEY=PUT-A-LONG-RANDOM-DJANGO-SECRET-HERE
DEBUG=False
ALLOWED_HOSTS=edoctorug.com,www.edoctorug.com

USSD_SHARED_SECRET=YOUR_REAL_USSD_SECRET
IPN_SHARED_SECRET=YOUR_REAL_IPN_SECRET

PUBLIC_BASE_URL=https://www.edoctorug.com

Do not commit this file to GitHub.

PythonAnywhere has documentation recommending environment variables for secrets such as Django's SECRET_KEY; their approach can load a .env file from the WSGI configuration.

5. Make one important improvement to settings.py

Your current:

DEBUG = config("DEBUG", default=True, cast=bool)

is dangerous if .env isn't loaded on production, because it can fall back to:

True

I would change your production-oriented configuration to:

DEBUG = config("DEBUG", default=False, cast=bool)

So your production server doesn't accidentally run with Django debug mode enabled.

Also change:

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost",
    cast=Csv()
)

This is fine because you'll supply the production value through .env.

6. Your recommended production settings.py

The relevant beginning of your file should become:

from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config(
    "SECRET_KEY",
    default="dev-only-change-me"
)

DEBUG = config(
    "DEBUG",
    default=False,
    cast=bool
)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost",
    cast=Csv()
)

USSD_SHARED_SECRET = config(
    "USSD_SHARED_SECRET",
    default="dev-secret"
)

IPN_SHARED_SECRET = config(
    "IPN_SHARED_SECRET",
    default="dev-ipn-secret"
)

PUBLIC_BASE_URL = config(
    "PUBLIC_BASE_URL",
    default="http://127.0.0.1:8000"
)

Everything else can initially remain as you have it.

7. Push the project to GitHub

From your project folder:

git status

Then:

git add .
git commit -m "Prepare Django application for deployment"
git push origin main

If your branch is called master, use:

git push origin master

PythonAnywhere provides Git in Bash consoles and supports cloning repositories from GitHub.

8. Create your PythonAnywhere account

Go to:

PythonAnywhere

Log in.

For a custom domain, you need an account/plan that supports custom-domain web apps. PythonAnywhere notes that free accounts have restrictions around custom domains, while paid accounts can run websites on domains they own.

9. Open a Bash console

Inside PythonAnywhere:

Dashboard → Consoles → Bash

You'll get something like:

yourusername@ssh:~$

Your username will be different.

10. Clone your GitHub repository

For a public GitHub repository:

cd ~
git clone https://github.com/YOUR-GITHUB-USERNAME/YOUR-REPOSITORY.git

For example:

cd ~
git clone https://github.com/edoctorug/edoctussd.git

Then:

cd ~/edoctussd

Check:

ls

You should see:

manage.py
edoctussd
dashboard
requirements.txt
...

If manage.py is inside another folder, stop here, because your paths will need to be adjusted.

11. Create the Python virtual environment

This is very important.

PythonAnywhere recommends using a virtual environment so your web application has its own Django/package versions.

First determine the Python version your project uses.

For example:

python3.12 --version

or:

python3.13 --version

Use the Python version supported by your PythonAnywhere account and compatible with your Django version.

For example:

mkvirtualenv edoctor-env --python=python3.12

Then:

workon edoctor-env

Check:

which python

You should get something similar to:

/home/YOURUSERNAME/.virtualenvs/edoctor-env/bin/python
12. Install your requirements

With the virtual environment active:

cd ~/edoctussd
pip install -r requirements.txt

Then check Django:

python -m django --version

And:

python --version
13. Create your production .env on PythonAnywhere

Now create the production environment file.

cd ~/edoctussd
nano .env

Put:

SECRET_KEY=YOUR_REAL_PRODUCTION_SECRET_KEY
DEBUG=False
ALLOWED_HOSTS=edoctorug.com,www.edoctorug.com

USSD_SHARED_SECRET=YOUR_REAL_USSD_SECRET
IPN_SHARED_SECRET=YOUR_REAL_IPN_SECRET

PUBLIC_BASE_URL=https://www.edoctorug.com

Save it.

If you don't want to use nano, you can use the PythonAnywhere Files interface to create .env.

Again, do not put this file into GitHub.

PythonAnywhere specifically documents loading .env values into the WSGI process for web applications.

14. Test Django before creating the web application

This is an important step.

Run:

cd ~/edoctussd
workon edoctor-env
python manage.py check

You ideally want:

System check identified no issues (0 silenced).

Then:

python manage.py migrate

Then:

python manage.py collectstatic

If prompted:

Type 'yes' to continue

enter:

yes

Your settings already have:

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

which is appropriate for collectstatic.

PythonAnywhere's static-file setup requires a STATIC_ROOT, running collectstatic, and then configuring a Static Files mapping in the Web tab.