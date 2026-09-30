cran_repo <- "https://cloud.r-project.org"
options(repos = c(CRAN = cran_repo))
options(timeout = max(300, getOption("timeout", 60)))

get_script_path <- function() {
  args_all <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args_all, value = TRUE)
  if (length(file_arg) > 0) {
    return(normalizePath(sub("^--file=", "", file_arg[1]), winslash = "/", mustWork = TRUE))
  }
  NULL
}

script_path <- get_script_path()

if (!is.null(script_path)) {
  project_root <- normalizePath(dirname(script_path), winslash = "/", mustWork = TRUE)
} else {
  cat("WARN: Cannot determine script path from --file. Falling back to current working directory.\n")
  project_root <- normalizePath(getwd(), winslash = "/", mustWork = TRUE)
}

lib_dir <- file.path(project_root, "env", "r_libs")
dir.create(lib_dir, recursive = TRUE, showWarnings = FALSE)
lib_dir <- normalizePath(lib_dir, winslash = "/", mustWork = TRUE)

# Keep the portable environment reproducible: user-level libraries must not
# satisfy project dependencies that will be absent on another machine.
system_libs <- unique(c(.Library.site, .Library))
system_libs <- system_libs[nzchar(system_libs)]
.libPaths(unique(c(lib_dir, system_libs)))

cat("==> Project root:\n")
cat(project_root, "\n\n")

cat("==> Using R private library:\n")
print(.libPaths())
cat("\n")

phase1_cran <- c(
  "data.table",
  "ggplot2",
  "pheatmap",
  "survival",
  "glmnet",
  "locfit",
  "timeROC",
  "pROC",
  "caret",
  "randomForest",
  "e1071",
  "dplyr",
  "patchwork"
)

phase2_bioc <- c(
  "limma",
  "org.Hs.eg.db",
  "org.Mm.eg.db"
)

phase3_cran <- c(
  "survminer",
  "msigdbr"
)

phase3_bioc <- c(
  "GSVA",
  "DESeq2",
  "clusterProfiler",
  "enrichplot"
)

phase4_cran <- c(
  "sp",
  "SeuratObject",
  "Seurat",
  "sctransform",
  "hdf5r"
)

required_dependencies <- function(pkg, lib.loc = NULL) {
  desc <- tryCatch(
    packageDescription(pkg, lib.loc = lib.loc),
    error = function(e) NULL,
    warning = function(w) NULL
  )
  if (is.null(desc)) return(character())

  fields <- unlist(desc[c("Depends", "Imports", "LinkingTo")], use.names = FALSE)
  fields <- fields[!is.na(fields) & nzchar(fields)]
  if (length(fields) == 0) return(character())

  entries <- trimws(unlist(strsplit(fields, ",", fixed = TRUE)))
  names <- trimws(sub("\\s*\\(.*$", "", entries))
  unique(setdiff(names[nzchar(names)], "R"))
}

dependency_tree_available <- function(pkg, lib.loc = NULL, seen = character()) {
  if (pkg %in% seen) return(TRUE)
  if (!requireNamespace(pkg, quietly = TRUE, lib.loc = lib.loc)) return(FALSE)

  deps <- required_dependencies(pkg, lib.loc = lib.loc)
  if (length(deps) == 0) return(TRUE)

  next_seen <- c(seen, pkg)
  all(vapply(
    deps,
    function(dep) dependency_tree_available(dep, seen = next_seen),
    logical(1)
  ))
}

is_installed <- function(pkg) {
  dependency_tree_available(pkg, lib.loc = lib_dir)
}

remove_lock_dirs <- function() {
  lock_dirs <- list.files(lib_dir, pattern = "^00LOCK", full.names = TRUE)
  if (length(lock_dirs) > 0) {
    cat("==> Removing stale lock directories:\n")
    print(lock_dirs)
    for (d in lock_dirs) {
      unlink(d, recursive = TRUE, force = TRUE)
    }
    cat("\n")
  }
}

configure_bioc_repos <- function() {
  if (!requireNamespace("BiocManager", quietly = TRUE, lib.loc = lib_dir)) {
    stop("BiocManager is not installed yet.")
  }

  bioc_repos <- BiocManager::repositories()
  bioc_repos["CRAN"] <- cran_repo
  options(repos = bioc_repos)

  cat("==> Active repositories:\n")
  print(getOption("repos"))
  cat("\n")
}

install_bioc_manager_if_needed <- function() {
  if (!is_installed("BiocManager")) {
    cat("==> Installing BiocManager...\n")
    install.packages("BiocManager", lib = lib_dir, repos = cran_repo)
  } else {
    cat("BiocManager already installed.\n")
  }

  configure_bioc_repos()
}

install_one_cran <- function(pkg) {
  if (is_installed(pkg)) {
    cat("[SKIP][CRAN] ", pkg, " already installed\n", sep = "")
    return(TRUE)
  }

  remove_lock_dirs()

  cat("[INSTALL][CRAN] ", pkg, "\n", sep = "")
  tryCatch(
    install.packages(
      pkg,
      lib = lib_dir,
      dependencies = NA,
      repos = cran_repo
    ),
    error = function(e) {
      cat("[ERROR][CRAN] ", pkg, ": ", conditionMessage(e), "\n", sep = "")
    }
  )

  if (is_installed(pkg)) {
    cat("[OK][CRAN] ", pkg, "\n", sep = "")
    TRUE
  } else {
    cat("[FAIL][CRAN] ", pkg, "\n", sep = "")
    FALSE
  }
}

install_one_bioc <- function(pkg) {
  if (is_installed(pkg)) {
    cat("[SKIP][BIOC] ", pkg, " already installed in private lib\n", sep = "")
    return(TRUE)
  }

  remove_lock_dirs()
  configure_bioc_repos()

  existing_path <- suppressWarnings(
    tryCatch(find.package(pkg), error = function(e) NA)
  )
  cat("[DEBUG][BIOC] existing path for ", pkg, ": ", existing_path, "\n", sep = "")

  cat("[INSTALL][BIOC] ", pkg, "\n", sep = "")
  tryCatch(
    BiocManager::install(
      pkg,
      lib = lib_dir,
      ask = FALSE,
      update = FALSE,
      force = TRUE,
      site_repository = character()
    ),
    error = function(e) {
      cat("[ERROR][BIOC] ", pkg, ": ", conditionMessage(e), "\n", sep = "")
    }
  )

  if (is_installed(pkg)) {
    cat("[OK][BIOC] ", pkg, "\n", sep = "")
    TRUE
  } else {
    cat("[FAIL][BIOC] ", pkg, "\n", sep = "")
    FALSE
  }
}

install_group <- function(pkgs, type = c("CRAN", "BIOC"), title = "Unnamed Phase") {
  type <- match.arg(type)

  cat("\n==================================================\n")
  cat("==> ", title, "\n", sep = "")
  cat("==================================================\n")

  results <- setNames(rep(FALSE, length(pkgs)), pkgs)

  if (length(pkgs) == 0) {
    cat("No packages in this phase.\n")
    return(results)
  }

  for (pkg in pkgs) {
    results[pkg] <- if (type == "CRAN") install_one_cran(pkg) else install_one_bioc(pkg)
  }

  cat("\n==> Phase summary: ", title, "\n", sep = "")
  print(results)

  failed <- names(results)[!results]
  if (length(failed) == 0) {
    cat("All packages in this phase installed successfully.\n")
  } else {
    cat("Failed packages in this phase:\n")
    print(failed)
  }

  invisible(results)
}

install_bioc_manager_if_needed()

results_phase1 <- install_group(
  phase1_cran,
  type = "CRAN",
  title = "Phase 1 - Core CRAN packages"
)

results_phase2 <- install_group(
  phase2_bioc,
  type = "BIOC",
  title = "Phase 2 - Core Bioconductor packages"
)

results_phase3_cran <- install_group(
  phase3_cran,
  type = "CRAN",
  title = "Phase 3A - Extended CRAN packages"
)

results_phase3_bioc <- install_group(
  phase3_bioc,
  type = "BIOC",
  title = "Phase 3B - Extended Bioconductor packages"
)

results_phase4 <- install_group(
  phase4_cran,
  type = "CRAN",
  title = "Phase 4 - Heavy single-cell packages"
)

all_results <- c(
  results_phase1,
  results_phase2,
  results_phase3_cran,
  results_phase3_bioc,
  results_phase4
)

cat("\n==================================================\n")
cat("==> FINAL INSTALLATION SUMMARY\n")
cat("==================================================\n")
print(all_results)

failed_all <- names(all_results)[!all_results]
success_all <- names(all_results)[all_results]

cat("\nInstalled successfully:\n")
print(success_all)

if (length(failed_all) == 0) {
  cat("\nAll packages are available in the project private library.\n")
} else {
  cat("\nStill missing packages:\n")
  print(failed_all)
  cat("\nTip: focus only on the failed packages next time; no need to reinstall everything.\n")
  quit(status = 1)
}
