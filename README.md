# HR Backend

Django-based HR management system backend.

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. **Activate the virtual environment:**
   ```bash
   # Windows
   .\venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create a `.env` file in the project root:**
   ```
   SECRET_KEY=your-secret-key-here
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   DATABASE_URL=sqlite:///db.sqlite3
   ```

4. **Initialize Django project (if not done yet):**
   ```bash
   django-admin startproject config .
   ```

5. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

6. **Create a superuser:**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the development server:**
   ```bash
   python manage.py runserver
   ```

The server will start at `http://127.0.0.1:8000/`

## Project Structure
```
HR Backend/
├── venv/                 # Virtual environment
├── config/               # Django project settings
├── apps/                 # Django applications
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables
├── .gitignore           # Git ignore file
└── manage.py            # Django management script
```

## Development

### Creating a new Django app
```bash
python manage.py startapp app_name
```

### Running tests
```bash
python manage.py test
```

### Making migrations
```bash
python manage.py makemigrations
python manage.py migrate
```
