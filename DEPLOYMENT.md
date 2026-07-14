# Deployment Guide

## Development vs Production

### Development Setup (Default)

```bash
# Install dependencies
pip install -r requirements.txt

# Run in development mode (with debug enabled)
python app.py
```

The app will start on `http://localhost:5000` with debug mode enabled for development.

### Production Deployment

For production environments, follow these security best practices:

#### 1. Set Environment Variables

```bash
# Set a secure secret key (generate a random string)
export SECRET_KEY="your-secure-random-secret-key-here"

# Disable debug mode
export FLASK_ENV="production"
```

To generate a secure secret key:
```python
python -c "import secrets; print(secrets.token_hex(32))"
```

#### 2. Use a Production WSGI Server

**Do NOT use the built-in Flask development server in production.**

Install a production-ready WSGI server like Gunicorn:

```bash
pip install gunicorn
```

Run with Gunicorn:
```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

Or with uWSGI:
```bash
pip install uwsgi
uwsgi --http :5000 --wsgi-file app.py --callable app --processes 4
```

#### 3. Use a Reverse Proxy

Set up Nginx or Apache as a reverse proxy in front of your application:

**Nginx Configuration Example:**
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /uploads/ {
        alias /path/to/card-grading-app/uploads/;
    }

    client_max_body_size 16M;
}
```

#### 4. Configure File Uploads

Ensure the uploads directory has proper permissions:

```bash
mkdir -p uploads
chmod 755 uploads
```

Consider storing uploads outside the application directory and using a CDN or object storage (S3, etc.) for production.

#### 5. Enable HTTPS

Use Let's Encrypt for free SSL certificates:

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

#### 6. Environment File

Create a `.env` file (never commit this to git):

```bash
# .env
SECRET_KEY=your-generated-secret-key-here
FLASK_ENV=production
UPLOAD_FOLDER=/var/www/card-grading-app/uploads
```

Load environment variables:
```bash
# Install python-dotenv
pip install python-dotenv

# In app.py, add at the top:
from dotenv import load_dotenv
load_dotenv()
```

#### 7. Systemd Service (Linux)

Create a systemd service file `/etc/systemd/system/card-grading.service`:

```ini
[Unit]
Description=Card Grading App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/card-grading-app
Environment="PATH=/var/www/card-grading-app/venv/bin"
Environment="SECRET_KEY=your-secret-key"
Environment="FLASK_ENV=production"
ExecStart=/var/www/card-grading-app/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable card-grading
sudo systemctl start card-grading
```

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

# Create uploads directory
RUN mkdir -p uploads && chmod 755 uploads

# Set environment variables
ENV FLASK_ENV=production
ENV SECRET_KEY=changeme

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  card-grading-app:
    build: .
    ports:
      - "5000:5000"
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - FLASK_ENV=production
    volumes:
      - ./uploads:/app/uploads
    restart: unless-stopped
```

Build and run:
```bash
# Set secret key in .env file
echo "SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')" > .env

# Build and start
docker-compose up -d
```

## Cloud Deployment Options

### Heroku

1. Create `Procfile`:
```
web: gunicorn app:app
```

2. Deploy:
```bash
heroku create your-app-name
heroku config:set SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
heroku config:set FLASK_ENV=production
git push heroku main
```

### AWS Elastic Beanstalk

1. Install EB CLI:
```bash
pip install awsebcli
```

2. Initialize and deploy:
```bash
eb init -p python-3.11 card-grading-app
eb create card-grading-env
eb setenv SECRET_KEY=your-secret-key FLASK_ENV=production
eb deploy
```

### Google Cloud Run

1. Create `Dockerfile` (see above)

2. Deploy:
```bash
gcloud builds submit --tag gcr.io/PROJECT-ID/card-grading-app
gcloud run deploy --image gcr.io/PROJECT-ID/card-grading-app --platform managed
```

## Security Checklist

- [ ] Set SECRET_KEY environment variable
- [ ] Set FLASK_ENV=production
- [ ] Use HTTPS/SSL in production
- [ ] Use a production WSGI server (not Flask dev server)
- [ ] Set up reverse proxy (Nginx/Apache)
- [ ] Configure firewall rules
- [ ] Limit file upload sizes
- [ ] Sanitize file uploads
- [ ] Regular security updates
- [ ] Monitor application logs
- [ ] Implement rate limiting
- [ ] Set up backup for uploads directory

## Performance Optimization

### Image Processing
- Consider using async workers for image processing
- Implement caching for repeated analyses
- Use CDN for static assets

### Database (Future Enhancement)
- Store grading history in database
- Cache frequently accessed data
- Use connection pooling

### Scaling
- Use load balancer for multiple instances
- Implement Redis for session storage
- Use message queue (Celery) for heavy processing

## Monitoring and Logging

### Application Logs
Configure proper logging:
```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
```

### Error Tracking
Consider integrating:
- Sentry for error tracking
- Prometheus for metrics
- Grafana for visualization

## Backup and Recovery

### Regular Backups
```bash
# Backup uploads directory
tar -czf uploads-backup-$(date +%Y%m%d).tar.gz uploads/

# Store in S3 or similar
aws s3 cp uploads-backup-*.tar.gz s3://your-bucket/backups/
```

### Database Backup (if implemented)
```bash
# Backup SQLite database
sqlite3 cards.db ".backup cards-backup-$(date +%Y%m%d).db"
```

## Troubleshooting Production Issues

### Check Logs
```bash
# Systemd service logs
sudo journalctl -u card-grading -f

# Nginx logs
sudo tail -f /var/log/nginx/error.log
```

### Common Issues
1. **502 Bad Gateway**: Check if app is running and port is correct
2. **File Upload Fails**: Check permissions and max upload size
3. **High Memory Usage**: Restart service, consider scaling
4. **Slow Response**: Check image processing, add caching

## Support

For production deployment assistance, open an issue on GitHub or consult the documentation.
