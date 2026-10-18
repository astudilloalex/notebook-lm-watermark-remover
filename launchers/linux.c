#define _GNU_SOURCE
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Always use the bundled interpreter rather than searching the system. */
int main(int argc, char **argv) {
    char root[PATH_MAX], python[PATH_MAX], entry[PATH_MAX];
    ssize_t count = readlink("/proc/self/exe", root, sizeof(root) - 1);
    if (count <= 0) return 1;
    root[count] = '\0';
    char *slash = strrchr(root, '/');
    if (!slash) return 1;
    *slash = '\0';
    if (snprintf(python, sizeof(python), "%s/runtime/bin/python3", root) >= sizeof(python)) return 1;
    if (snprintf(entry, sizeof(entry), "%s/app/desktop_entry.py", root) >= sizeof(entry)) return 1;
    char **arguments = calloc((size_t)argc + 4, sizeof(char *));
    if (!arguments) return 1;
    arguments[0] = python; arguments[1] = "-I"; arguments[2] = "-B"; arguments[3] = entry;
    for (int i = 1; i < argc; i++) arguments[i + 3] = argv[i];
    execv(python, arguments);
    perror("Could not open NotebookLM Studio");
    return 1;
}
