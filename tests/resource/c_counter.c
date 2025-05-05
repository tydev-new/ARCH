#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <string.h> // For strerror
#include <errno.h>  // For errno

int main() {
    fprintf(stderr, "C program starting on host (or container). Attempting to open /output.log\n");

    int log_fd = open("output.log", O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (log_fd < 0) {
       // Print error to original stderr BEFORE trying to redirect
       fprintf(stderr, "Error opening /output.log: %s\n", strerror(errno));
       // Optionally exit, or try to continue without logging
       // For this test, let's exit if we can't log
       return 1;
    }
    fprintf(stderr, "Successfully opened output.log with fd %d\n", log_fd);

    fprintf(stderr, "Attempting dup2 to stdout...\n");
    if (dup2(log_fd, STDOUT_FILENO) < 0) {
         fprintf(stderr, "Error dup2(log_fd, STDOUT_FILENO): %s\n", strerror(errno));
         close(log_fd);
         return 1;
    }

    fprintf(stderr, "Attempting dup2 to stderr...\n");
    if (dup2(log_fd, STDERR_FILENO) < 0) {
         // Can't report this error easily as stderr redirection itself failed
         // Original stderr might already be closed or redirected by the caller
         close(log_fd); // Try to close the log fd
         return 1;
    }

    // Close original log_fd ONLY AFTER successful dup2 for both stdout/stderr
    close(log_fd);
    fprintf(stdout, "Redirected stdout/stderr to output.log\n"); // Goes to file now
    fflush(stdout);


    // Redirect stdin from /dev/null (less critical, but good practice)
    int null_fd = open("/dev/null", O_RDONLY);
    if (null_fd >= 0) {
        if (dup2(null_fd, STDIN_FILENO) < 0) {
             fprintf(stdout, "Warning: dup2(null_fd, STDIN_FILENO) failed: %s\n", strerror(errno)); // To file
             fflush(stdout);
        }
        close(null_fd);
    } else {
         fprintf(stdout, "Warning: open /dev/null failed: %s\n", strerror(errno)); // To file
         fflush(stdout);
    }


    fprintf(stdout, "C program setup complete. Entering loop.\n");
    fflush(stdout);

    time_t rawtime;
    struct tm * timeinfo;
    char buffer [80];
    unsigned long long count = 0;

    while (count<600) {
        time (&rawtime);
        timeinfo = localtime (&rawtime);
        strftime (buffer,80,"%c",timeinfo);

        fprintf(stdout, "Count %llu alive at %s\n", count, buffer);
        fflush(stdout);
        sleep(3);
        count++;
    }

    return 0; 
}