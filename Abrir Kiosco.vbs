Set WshShell = CreateObject("WScript.Shell")
carpeta = WshShell.CurrentDirectory
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
python = base & "\.venv\Scripts\pythonw.exe"
script = base & "\kiosco.py"
WshShell.Run """" & python & """ """ & script & """", 0, False
