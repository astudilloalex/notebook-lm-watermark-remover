/* 64-bit PE launcher using Win32 directly, without a CRT or system Python. */
typedef unsigned long DWORD;
typedef unsigned short WORD;
typedef unsigned short WCHAR;
typedef int BOOL;
typedef void *HANDLE;
typedef struct {
    DWORD cb;
    WCHAR *lpReserved, *lpDesktop, *lpTitle;
    DWORD dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars;
    DWORD dwFillAttribute, dwFlags;
    WORD wShowWindow, cbReserved2;
    unsigned char *lpReserved2;
    HANDLE hStdInput, hStdOutput, hStdError;
} STARTUPINFO;
typedef struct { HANDLE hProcess, hThread; DWORD dwProcessId, dwThreadId; } PROCESSINFO;
typedef char check_startupinfo_size[(sizeof(STARTUPINFO) == 104) ? 1 : -1];
__declspec(dllimport) DWORD GetModuleFileNameW(HANDLE, WCHAR *, DWORD);
__declspec(dllimport) WCHAR *GetCommandLineW(void);
__declspec(dllimport) BOOL CreateProcessW(const WCHAR *, WCHAR *, void *, void *, BOOL, DWORD, void *, const WCHAR *, STARTUPINFO *, PROCESSINFO *);
__declspec(dllimport) BOOL CloseHandle(HANDLE);
__declspec(dllimport) void ExitProcess(DWORD);
__declspec(dllimport) int MessageBoxW(HANDLE, const WCHAR *, const WCHAR *, unsigned int);
static WCHAR root[32768], python[32768], entry[32768], command[32768];
static STARTUPINFO startup;
static PROCESSINFO process;
static unsigned int append(WCHAR *to, unsigned int pos, const WCHAR *from) {
    for (unsigned int i = 0; from[i] && pos < 32766; i++) to[pos++] = from[i];
    to[pos] = 0;
    return pos;
}
static void fail(void) {
    MessageBoxW(0, (const WCHAR *)L"Could not open the application. Reinstall it or extract the complete portable folder.", (const WCHAR *)L"NotebookLM Studio", 0x10);
    ExitProcess(1);
}
void start(void) {
    DWORD length = GetModuleFileNameW(0, root, 32768);
    if (!length || length >= 16000) fail();
    while (length && root[length - 1] != '\\') length--;
    if (!length) fail();
    root[length] = 0;
    append(python, append(python, 0, root), (const WCHAR *)L"runtime\\pythonw.exe");
    append(entry, append(entry, 0, root), (const WCHAR *)L"app\\desktop_entry.py");
    unsigned int pos = append(command, 0, (const WCHAR *)L"\"");
    pos = append(command, pos, python);
    pos = append(command, pos, (const WCHAR *)L"\" -I \"");
    pos = append(command, pos, entry);
    pos = append(command, pos, (const WCHAR *)L"\"");
    /* Forward arguments such as --sin-abrir for CI checks. */
    WCHAR *args = GetCommandLineW();
    if (*args == '"') { args++; while (*args && *args != '"') args++; if (*args) args++; }
    else { while (*args && *args != ' ' && *args != '\t') args++; }
    while (*args == ' ' || *args == '\t') args++;
    if (*args) append(command, append(command, pos, (const WCHAR *)L" "), args);
    startup.cb = sizeof(startup);
    if (!CreateProcessW(python, command, 0, 0, 0, 0x08000000, 0, root, &startup, &process)) fail();
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    ExitProcess(0);
}
