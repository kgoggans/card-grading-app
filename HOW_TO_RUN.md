# How to Run the Card Grading App

## Quick Answer: Where Do I Run This?

**YES, you can run this in VS Code!** 

You can also run it from:
- ✅ **VS Code** (recommended for beginners)
- ✅ **Command Line / Terminal** (any OS)
- ✅ **PyCharm** or other Python IDEs
- ✅ **Windows Command Prompt or PowerShell**
- ✅ **Mac Terminal**
- ✅ **Linux Terminal**

---

## 🚀 Method 1: Running in VS Code (Recommended for Beginners)

### Step 1: Open the Project in VS Code

1. **Open VS Code**
2. Click **File** → **Open Folder**
3. Navigate to and select the `card-grading-app` folder
4. Click **Select Folder**

### Step 2: Open the Terminal in VS Code

- Press `` Ctrl + ` `` (backtick) or
- Click **View** → **Terminal** from the menu
- Or click **Terminal** → **New Terminal**

You'll see a terminal panel at the bottom of VS Code.

### Step 3: Install Dependencies

In the VS Code terminal, type:

```bash
pip install -r requirements.txt
```

Press Enter and wait for installation to complete.

### Step 4: Run the Application

In the same terminal, type:

```bash
python app.py
```

Press Enter.

### Step 5: Open in Your Browser

You'll see output like:
```
 * Running on http://127.0.0.1:5000
```

**Either:**
- Hold `Ctrl` (or `Cmd` on Mac) and click the URL in the terminal, **OR**
- Open your web browser and go to: `http://localhost:5000`

### Step 6: Use the App

- Upload front and back images of your card
- Click "Grade My Card"
- View your results!

### Step 7: Stop the Application

When done, press `Ctrl + C` in the VS Code terminal to stop the server.

---

## 💻 Method 2: Running from Command Line / Terminal

### Windows (Command Prompt or PowerShell)

1. **Open Command Prompt:**
   - Press `Win + R`
   - Type `cmd` and press Enter

2. **Navigate to the project folder:**
   ```cmd
   cd C:\path\to\card-grading-app
   ```

3. **Install dependencies:**
   ```cmd
   pip install -r requirements.txt
   ```

4. **Run the app:**
   ```cmd
   python app.py
   ```

5. **Open browser to:** `http://localhost:5000`

### Mac / Linux (Terminal)

1. **Open Terminal:**
   - Mac: `Cmd + Space`, type "Terminal", press Enter
   - Linux: `Ctrl + Alt + T`

2. **Navigate to the project folder:**
   ```bash
   cd /path/to/card-grading-app
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   
   Or if using Python 3:
   ```bash
   pip3 install -r requirements.txt
   ```

4. **Run the app:**
   ```bash
   python app.py
   ```
   
   Or if using Python 3:
   ```bash
   python3 app.py
   ```

5. **Open browser to:** `http://localhost:5000`

---

## 🐍 Method 3: Running in PyCharm

### Step 1: Open Project

1. Open PyCharm
2. Click **File** → **Open**
3. Select the `card-grading-app` folder
4. Click **OK**

### Step 2: Install Dependencies

1. Open the Terminal in PyCharm (bottom of window)
2. Run:
   ```bash
   pip install -r requirements.txt
   ```

### Step 3: Run the Application

**Option A: Using Terminal**
1. In the PyCharm terminal, run:
   ```bash
   python app.py
   ```

**Option B: Using Run Configuration**
1. Right-click on `app.py` in the Project panel
2. Select **Run 'app'**

### Step 4: Access the App

Open your browser to: `http://localhost:5000`

---

## 🔧 Method 4: Using Python Virtual Environment (Recommended for Advanced Users)

Virtual environments keep your project dependencies isolated.

### Windows

```cmd
# Navigate to project folder
cd C:\path\to\card-grading-app

# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

### Mac / Linux

```bash
# Navigate to project folder
cd /path/to/card-grading-app

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

To deactivate the virtual environment when done:
```bash
deactivate
```

---

## 📱 What You Should See

### In Your Terminal/Console:

```
 * Serving Flask app 'app'
 * Debug mode: on
WARNING: This is a development server...
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://10.x.x.x:5000
Press CTRL+C to quit
```

### In Your Browser:

You should see:
- 🏆 **Sports Card Grading App** header
- Instructions on how to use
- Two upload boxes (Front of Card / Back of Card)
- "Grade My Card" button

---

## ❓ Troubleshooting

### "python is not recognized" or "command not found"

**Problem:** Python is not installed or not in your PATH.

**Solution:**
1. Download Python from [python.org](https://www.python.org/downloads/)
2. During installation, check **"Add Python to PATH"**
3. Restart your terminal/VS Code after installation

### "No module named 'flask'" or similar errors

**Problem:** Dependencies are not installed.

**Solution:**
```bash
pip install -r requirements.txt
```

If that doesn't work, try:
```bash
python -m pip install -r requirements.txt
```

Or:
```bash
pip3 install -r requirements.txt
```

### "Address already in use" or "Port 5000 is already allocated"

**Problem:** Another application is using port 5000.

**Solution 1:** Stop other applications using port 5000

**Solution 2:** Use a different port by editing `app.py`:
```python
# At the bottom of app.py, change:
app.run(debug=True, host='0.0.0.0', port=5000)
# To:
app.run(debug=True, host='0.0.0.0', port=5001)
```

Then access at: `http://localhost:5001`

### "Permission denied" errors

**Problem:** Insufficient permissions.

**Solution (Windows):**
- Run Command Prompt or VS Code as Administrator

**Solution (Mac/Linux):**
- Use `sudo`:
  ```bash
  sudo pip install -r requirements.txt
  ```

### VS Code terminal not working

**Problem:** Terminal panel doesn't appear.

**Solution:**
1. Press `` Ctrl + Shift + P `` (or `Cmd + Shift + P` on Mac)
2. Type "Terminal: Create New Terminal"
3. Press Enter

---

## 🎯 Quick Reference

| What | Command |
|------|---------|
| Install dependencies | `pip install -r requirements.txt` |
| Run the app | `python app.py` |
| Access in browser | `http://localhost:5000` |
| Stop the app | `Ctrl + C` in terminal |
| VS Code terminal | `` Ctrl + ` `` |

---

## 🌟 Best Practices

1. **Use VS Code for beginners** - It's user-friendly with integrated terminal
2. **Use virtual environments** - Keeps dependencies isolated
3. **Check Python version** - Run `python --version` (should be 3.8+)
4. **Keep terminal open** - Don't close it while app is running
5. **Use localhost:5000** - Not just 127.0.0.1:5000

---

## 🆘 Still Having Issues?

1. **Check the logs** - Read error messages in the terminal carefully
2. **Verify Python installation** - Run `python --version`
3. **Verify pip installation** - Run `pip --version`
4. **Check file location** - Make sure you're in the correct folder
5. **Try restarting** - Close everything and try again

For more help:
- See [QUICKSTART.md](QUICKSTART.md) for detailed usage
- See [README.md](README.md) for full documentation
- See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment

---

## 💡 Summary

**The simplest way:**
1. Open VS Code
2. Open the project folder
3. Open terminal in VS Code (`` Ctrl + ` ``)
4. Run `pip install -r requirements.txt`
5. Run `python app.py`
6. Open `http://localhost:5000` in your browser

**That's it!** 🎉
