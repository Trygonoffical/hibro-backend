#!/bin/bash
set -e

echo "Deployment started ..."

# Pull the latest version of the app
git pull origin main
echo "New changes copied to server !"

# Activate Virtual Env
source /home/ardas/hibro/backend/actions-runner/_work/hibro-backend/env/bin/activate
echo "Virtual env 'env' Activated !"

echo "Installing Dependencies..."
pip install -r /home/ardas/hibro/backend/actions-runner/_work/hibro-backend/hibro-backend/requirements.txt --no-input

echo "Serving Static Files..."
python3 /home/ardas/hibro/backend/actions-runner/_work/hibro-backend/hibro-backend/manage.py collectstatic --noinput

echo "Running Database migration"
python3 /home/ardas/hibro/backend/actions-runner/_work/hibro-backend/hibro-backend/manage.py makemigrations
python3 /home/ardas/hibro/backend/actions-runner/_work/hibro-backend/hibro-backend/manage.py migrate

# Deactivate Virtual Env
deactivate
echo "Virtual env 'env' Deactivated !"

# Reload Gunicorn service to reflect new changes
echo "Reloading Gunicorn service..."
sudo systemctl restart gunicorn

echo "Deployment Finished!"
