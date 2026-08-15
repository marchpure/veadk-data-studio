use std::env;
use std::fs;
use std::io::Write;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::Command;

// This macro will embed the tarball at compile time.
// Make sure 'backend.tar.gz' exists in the same directory or relative path when compiling.
const COMPRESSED_BACKEND: &[u8] = include_bytes!("backend.tar.gz");
const APP_VERSION: &str = env!("APP_VERSION");

fn main() {
    // 1. Determine the extraction directory: ~/Library/Application Support/com.byaan.desktop/runtime/<version>
    let home_dir = env::var("HOME").expect("HOME environment variable not set");
    let app_support = PathBuf::from(home_dir).join("Library/Application Support/com.byaan.desktop/runtime").join(APP_VERSION);
    let backend_executable = app_support.join("backend/backend");

    // 2. Check if the backend is already extracted and exists
    if !backend_executable.exists() {
        let runtime_dir = app_support.parent().expect("Failed to get runtime directory");
        if runtime_dir.exists() {
            if let Ok(entries) = fs::read_dir(runtime_dir) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if path.is_dir() && path != app_support {
                        eprintln!("Removing old backend version: {:?}", path.file_name().unwrap_or_default());
                        let _ = fs::remove_dir_all(&path);
                    }
                }
            }
        }

        eprintln!("Extracting backend to: {:?}", app_support);
        fs::create_dir_all(&app_support).expect("Failed to create runtime directory");

        // 3. Extract the tarball
        // We will write the tarball to a temp file and then untar it, or pipe it to tar.
        // Piping is cleaner but requires managing stdin. Writing to a temp file is safer for a simple script.
        let tarball_path = app_support.join("backend.tar.gz");
        {
            let mut file = fs::File::create(&tarball_path).expect("Failed to create temp tarball");
            file.write_all(COMPRESSED_BACKEND).expect("Failed to write tarball");
        }

        // Run tar -xzf backend.tar.gz -C .
        let status = Command::new("tar")
            .arg("-xzf")
            .arg(&tarball_path)
            .arg("-C")
            .arg(&app_support)
            .status()
            .expect("Failed to execute tar");

        if !status.success() {
            eprintln!("Failed to extract backend tarball");
            std::process::exit(1);
        }

        // Clean up tarball
        let _ = fs::remove_file(&tarball_path);

        // 4. Clear quarantine attributes (xattr -cr)
        // This is critical for macOS to allow the binaries to run without "damaged" errors
        let status_xattr = Command::new("xattr")
            .arg("-cr")
            .arg(app_support.join("backend"))
            .status()
            .expect("Failed to execute xattr");
            
        if !status_xattr.success() {
            eprintln!("Warning: Failed to clear extended attributes");
        }
        
        eprintln!("Backend extracted successfully.");
    } else {
        // Backend already exists, we can skip extraction
        // eprintln!("Backend found, skipping extraction.");
    }

    // 5. Execute the backend
    // We replace the current process with the backend process
    let args: Vec<String> = env::args().skip(1).collect();
    let err = Command::new(&backend_executable)
        .args(args)
        .exec();

    eprintln!("Failed to launch backend: {}", err);
    std::process::exit(1);
}
