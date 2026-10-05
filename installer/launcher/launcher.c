/* ReelMaker.exe: runs Reel Maker inside this process using the bundled Python,
   so Windows shows (and pins) the app as Reel Maker with its own icon.
   Lives next to python312.dll in <install>\python\ and starts ..\app\launch.pyw. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdlib.h>
#include <wchar.h>

typedef int (*PyMainFn)(int, wchar_t **);

static void fail(const wchar_t *msg) {
    MessageBoxW(NULL, msg, L"Reel Maker", MB_OK | MB_ICONERROR);
}

int WINAPI wWinMain(HINSTANCE h, HINSTANCE prev, PWSTR cmd, int show) {
    wchar_t exe[MAX_PATH], dir[MAX_PATH], dll[MAX_PATH], script[MAX_PATH];
    GetModuleFileNameW(NULL, exe, MAX_PATH);
    wcscpy(dir, exe);
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = 0;

    _snwprintf(dll, MAX_PATH, L"%ls\\python312.dll", dir);
    _snwprintf(script, MAX_PATH, L"%ls\\..\\app\\launch.pyw", dir);
    wchar_t full[MAX_PATH];
    if (GetFullPathNameW(script, MAX_PATH, full, NULL)) wcscpy(script, full);

    /* A windowed program has no console, so give Python's stdin/stdout/stderr
       the NUL device instead of invalid handles (otherwise Python stops at startup). */
    static const DWORD ids[3] = {STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE};
    for (int i = 0; i < 3; i++) {
        HANDLE hd = GetStdHandle(ids[i]);
        if (hd == NULL || hd == INVALID_HANDLE_VALUE || GetFileType(hd) == FILE_TYPE_UNKNOWN) {
            HANDLE nul = CreateFileW(L"NUL", i == 0 ? GENERIC_READ : GENERIC_WRITE,
                                     FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
            if (nul != INVALID_HANDLE_VALUE) SetStdHandle(ids[i], nul);
        }
    }

    SetDllDirectoryW(dir);
    HMODULE py = LoadLibraryW(dll);
    if (!py) { fail(L"Reel Maker couldn't start because some of its files are missing.\nPlease reinstall it."); return 1; }
    PyMainFn py_main = (PyMainFn)GetProcAddress(py, "Py_Main");
    if (!py_main) { fail(L"Reel Maker couldn't start (Python is damaged). Please reinstall it."); return 1; }

    /* argv: ReelMaker.exe -I <script> [anything passed to us, e.g. a video file] */
    int n = 0;
    wchar_t **in = CommandLineToArgvW(GetCommandLineW(), &n);
    wchar_t **argv = (wchar_t **)calloc((size_t)n + 3, sizeof(wchar_t *));
    int argc = 0;
    argv[argc++] = exe;
    argv[argc++] = L"-I";
    argv[argc++] = script;
    for (int i = 1; i < n; i++) argv[argc++] = in[i];
    argv[argc] = NULL;
    return py_main(argc, argv);
}
