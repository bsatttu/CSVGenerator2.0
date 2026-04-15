Set WshShell = CreateObject("WScript.Shell")
projectDir = "F:\Projects\CSVGenerator2.0"
batchFile = """" & projectDir & "\CSVGenerator.bat"""

WshShell.CurrentDirectory = projectDir
WshShell.Run "cmd /c " & batchFile, 0, False
