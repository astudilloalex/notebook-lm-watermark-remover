; Built with the Inno Setup compiler supplied by the Windows Actions runner.
[Setup]
AppId=NotebookLMStudio
AppName=NotebookLM Studio
AppVersion={#AppVersion}
AppPublisher=Alex Astudillo
AppPublisherURL=https://github.com/astudilloalex/notebook-lm-watermark-remover
AppSupportURL=https://github.com/astudilloalex/notebook-lm-watermark-remover/issues
DefaultDirName={localappdata}\Programs\NotebookLM Studio
DefaultGroupName=NotebookLM Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=NotebookLM-Studio-{#AppVersion}-Windows-x64-Setup
SetupIconFile={#IconPath}
UninstallDisplayIcon={app}\NotebookLM Studio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#PayloadPath}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\NotebookLM Studio"; Filename: "{app}\NotebookLM Studio.exe"
Name: "{autodesktop}\NotebookLM Studio"; Filename: "{app}\NotebookLM Studio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NotebookLM Studio.exe"; Description: "Open NotebookLM Studio"; Flags: nowait postinstall skipifsilent
