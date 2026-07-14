# VS Code Setup Guide - "I Don't See the Folder"

## 🔍 Problem: Can't Find card-grading-app Folder in VS Code

If you can't see the `card-grading-app` folder in VS Code, this guide will help you locate and open it properly.

---

## ✅ Quick Solution

**The folder needs to be OPENED in VS Code, not just visible in the file system.**

Follow these steps:

### Step 1: Find Where You Downloaded/Cloned the Project

#### If You Downloaded as ZIP:
1. Go to your **Downloads** folder
2. Look for `card-grading-app-main.zip` or similar
3. **Right-click** → **Extract All** (Windows) or **Double-click** (Mac)
4. Note the location where it extracted (usually `Downloads/card-grading-app-main/`)

#### If You Cloned with Git:
1. Remember where you ran `git clone`
2. Common locations:
   - **Windows**: `C:\Users\YourName\Documents\card-grading-app`
   - **Mac**: `/Users/YourName/Documents/card-grading-app`
   - **Linux**: `/home/YourName/card-grading-app`

### Step 2: Open the Folder in VS Code

**Method A: From VS Code**
1. Open VS Code
2. Click **File** → **Open Folder** (or `Ctrl+K Ctrl+O` on Windows/Linux, `Cmd+K Cmd+O` on Mac)
3. Navigate to where you found the folder in Step 1
4. Select the **card-grading-app** folder (or card-grading-app-main)
5. Click **Select Folder** (Windows) or **Open** (Mac)

**Method B: From File Explorer/Finder**
1. Navigate to the folder location from Step 1
2. **Right-click** on the `card-grading-app` folder
3. Select **Open with Code** (if available)

**Method C: Drag and Drop**
1. Open VS Code
2. Open File Explorer (Windows) or Finder (Mac)
3. Drag the `card-grading-app` folder onto VS Code window

---

## 🎯 What You Should See After Opening

Once properly opened, VS Code should show:

```
VS Code Window Title:
card-grading-app - Visual Studio Code

Left Sidebar (Explorer):
📁 CARD-GRADING-APP
├── 📄 app.py
├── 📄 grading_system.py
├── 📄 image_analysis.py
├── 📄 requirements.txt
├── 📄 README.md
├── 📁 templates
│   ├── index.html
│   └── about.html
└── 📁 uploads
```

**If you see this, you're ready to go!**

---

## ❌ Common Problems & Solutions

### Problem 1: "I only see a single file, not the folder"

**Cause:** You opened a file instead of the folder.

**Solution:**
1. Click **File** → **Close Folder** or **Close Window**
2. Click **File** → **Open Folder** (NOT "Open File")
3. Select the entire **card-grading-app** folder

---

### Problem 2: "The folder is empty or I only see .git or hidden files"

**Cause:** You haven't cloned/downloaded the project yet, or you're in the wrong folder.

**Solution:**

**Option A: Download the Project**
1. Go to: https://github.com/kgoggans/card-grading-app
2. Click the green **Code** button
3. Click **Download ZIP**
4. Extract the ZIP file
5. Open the extracted folder in VS Code

**Option B: Clone with Git**
1. Open VS Code terminal (`Ctrl + ``)
2. Navigate to where you want the project:
   ```bash
   cd Documents  # or another location
   ```
3. Clone the repository:
   ```bash
   git clone https://github.com/kgoggans/card-grading-app.git
   ```
4. Open the folder:
   - Click **File** → **Open Folder**
   - Select the `card-grading-app` folder that was just created

---

### Problem 3: "I extracted the ZIP but there's a double folder"

**Cause:** ZIP files often extract with an extra wrapper folder.

**Example structure:**
```
Downloads/
└── card-grading-app-main/          ← Outer folder (what you see first)
    └── card-grading-app-main/      ← Inner folder (the actual project)
        ├── app.py
        ├── requirements.txt
        └── ...
```

**Solution:**
Open the **inner** folder (the one that contains `app.py`, not the wrapper).

**How to tell which is which:**
- ✅ **Correct folder**: Contains `app.py`, `requirements.txt`, `templates/` folder
- ❌ **Wrong folder**: Contains only another folder with the same name

---

### Problem 4: "The Explorer panel is collapsed or hidden"

**Cause:** The Explorer sidebar might be hidden.

**Solution:**
1. Press `Ctrl+Shift+E` (Windows/Linux) or `Cmd+Shift+E` (Mac)
2. Or click the **Explorer icon** (📁) at the top of the left sidebar
3. Or go to **View** → **Explorer**

---

### Problem 5: "Permission denied or can't access the folder"

**Cause:** The folder might be in a protected location.

**Solution:**
1. Move the folder to your **Documents** or **Desktop** folder
2. Try opening it again
3. On Windows, ensure you're not opening from a zip directly (extract first)

---

## 📋 Step-by-Step Checklist

Use this checklist to ensure proper setup:

- [ ] I have downloaded or cloned the repository
- [ ] I extracted the ZIP file (if downloaded as ZIP)
- [ ] I know the exact path where the folder is located
- [ ] I opened VS Code
- [ ] I used **File → Open Folder** (not Open File)
- [ ] I selected the folder containing `app.py` and `requirements.txt`
- [ ] I can see the file list in the Explorer panel (left sidebar)
- [ ] The VS Code window title shows "card-grading-app"
- [ ] I can see `app.py`, `grading_system.py`, and `templates/` folder

**If all boxes are checked, you're ready to proceed!**

---

## 🚀 Next Steps After Opening the Folder

Once you can see the folder in VS Code:

1. **Open the Terminal:**
   - Press `` Ctrl + ` `` (backtick)
   - Or click **Terminal** → **New Terminal**

2. **Verify you're in the right location:**
   ```bash
   # Windows
   dir
   
   # Mac/Linux
   ls
   ```
   
   You should see `app.py`, `requirements.txt`, etc.

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app:**
   ```bash
   python app.py
   ```

5. **Open browser:**
   Go to `http://localhost:5000`

---

## 🎓 Visual Guide: What Opening a Folder Looks Like

### WRONG ❌ - File is open, not folder
```
VS Code Window:
┌─────────────────────────────────────┐
│ app.py - Visual Studio Code    [_][○][X] │
├─────────────────────────────────────┤
│ No Explorer panel visible            │
│ Just one file open in editor         │
│                                      │
│  # app.py contents...                │
│  from flask import Flask...          │
└─────────────────────────────────────┘
```

### CORRECT ✅ - Folder is open
```
VS Code Window:
┌─────────────────────────────────────────────┐
│ card-grading-app - Visual Studio Code  [_][○][X] │
├────────────┬────────────────────────────────┤
│ 📁 EXPLORER │ Welcome / Get Started          │
│            │                                │
│ CARD-GRADI │                                │
│ NG-APP     │ Open a file to get started     │
│ ├─ 📄 app.py                               │
│ ├─ 📄 gradi                                │
│ ├─ 📄 image                                │
│ ├─ 📄 requi                                │
│ ├─ 📁 templ                                │
│ └─ 📁 uploa                                │
└────────────┴────────────────────────────────┘
```

---

## 🆘 Still Can't Find It?

### Try This: Create a New, Clean Setup

1. **Create a new folder on your Desktop:**
   - Right-click Desktop → New → Folder
   - Name it `my-card-grading-app`

2. **Download the project fresh:**
   - Go to: https://github.com/kgoggans/card-grading-app
   - Click **Code** → **Download ZIP**

3. **Extract directly to your new folder:**
   - Open the ZIP file
   - Copy everything inside to `my-card-grading-app`

4. **Open in VS Code:**
   - Open VS Code
   - File → Open Folder
   - Select `my-card-grading-app`

5. **Verify:**
   - You should see `app.py` in the Explorer panel
   - Window title should show `my-card-grading-app`

---

## 💡 Pro Tips

1. **Use Recent Folders**: Once opened once, use **File → Open Recent** to quickly reopen
2. **Add to Workspace**: Right-click the folder in Explorer and select **Add Folder to Workspace**
3. **Bookmark**: Add the folder path to your browser bookmarks or desktop shortcut
4. **Terminal Test**: In VS Code terminal, run `ls` (Mac/Linux) or `dir` (Windows) to see files

---

## 📚 Related Documentation

- **[HOW_TO_RUN.md](HOW_TO_RUN.md)** - Complete running instructions
- **[QUICKSTART.md](QUICKSTART.md)** - Quick start guide
- **[README.md](README.md)** - Project overview

---

## 🎯 Summary

**Key Point:** VS Code needs the folder to be **OPENED**, not just browsed to.

**The folder is open correctly when:**
- ✅ Window title shows "card-grading-app"
- ✅ Explorer panel shows all files (app.py, requirements.txt, etc.)
- ✅ You can open the terminal and it starts in the project folder

**Common mistake:** Opening a single file instead of the whole folder.

**Solution:** File → Open Folder → Select the card-grading-app folder → Click Open

---

**Still stuck?** Check that you've actually downloaded/cloned the project first, then use the step-by-step checklist above!
