Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
ScriptDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptDir

' Launch Start_Farmer.bat completely hidden (0 = hide window)
WshShell.Run "cmd.exe /c Start_Farmer.bat", 0, False
