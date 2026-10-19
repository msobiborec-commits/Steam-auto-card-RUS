Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptDir

pyw = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe")
If FSO.FileExists(pyw) Then
    WshShell.Run """" & pyw & """ main.py", 0, False
    WScript.Quit
End If

On Error Resume Next
WshShell.Run "pythonw main.py", 0, False
If Err.Number <> 0 Then
    Err.Clear
    WshShell.Run "pyw main.py", 0, False
End If
