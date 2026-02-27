import os, subprocess, tempfile

repo      = r"i:\Work\Dev\Repos\AI_Meetings"
installer = repo + r"\installer"
dist      = repo + r"\dist"
iscc      = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe")

with open(installer + r"\setup.iss", encoding="utf-8") as f:
    content = f.read()

content = content.replace("OutputDir=..\\dist",            "OutputDir=" + dist)
content = content.replace("LicenseFile=..\\LICENSE.txt",   "LicenseFile=" + repo + "\\LICENSE.txt")
content = content.replace("SetupIconFile=assets\\",        "SetupIconFile=" + installer + "\\assets\\")
content = content.replace("WizardImageFile=assets\\",      "WizardImageFile=" + installer + "\\assets\\")
content = content.replace("WizardSmallImageFile=assets\\", "WizardSmallImageFile=" + installer + "\\assets\\")
content = content.replace('Source: "..\\dist\\',           'Source: "' + dist + '\\')
content = content.replace('Source: "bundled\\',            'Source: "' + installer + '\\bundled\\')
content = content.replace('Source: "assets\\',             'Source: "' + installer + '\\assets\\')

tmp = tempfile.NamedTemporaryFile(suffix=".iss", delete=False, mode="w", encoding="utf-8")
tmp.write(content)
tmp.close()
print("Temp .iss:", tmp.name)

result = subprocess.run([iscc, tmp.name])
print("Exit code:", result.returncode)
os.unlink(tmp.name)
