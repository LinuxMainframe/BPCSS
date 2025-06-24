# BioPhysics Computation Server System (BPCSS)

**BPCSS** is a reproducible, modular, and interactive pipeline for academic all-atom molecular dynamics (MD) simulations and structure preparation. It streamlines protein cleanup, loop modeling, validation, and integration with downstream tools (e.g., GROMACS, CHARMM-GUI) via Python automation. Originally designed for GPCRs (e.g., 5-HT₂A receptor, PDB: 6A94), it is extensible to other membrane proteins, ligand-bound receptors, and complexes.

---

## ✨ Key Features

- **Interactive REPL** with commands:
  - `show` / `info`: display saved system information
  - `clear`: clear the terminal screen
  - `pp`: launch the protein preparation sub-module
  - `help` / `?`: list available commands
  - `exit` / `quit`: exit the toolkit
- **System information gathering**:
  - CPU, RAM, OS details, GPU detection (NVIDIA/AMD), PATH checks, GROMACS (`gmx`) availability, CUDA toolkit presence, CPU flags analysis, etc.
  - Detects changes between runs and prompts user on how to handle them.
- **Protein preparation workflow** (`pp`):
  1. **Input choice**: local PDB file or fetch from RCSB by PDB ID.
  2. **Parsing & cleanup**:
     - List chains and HETATM entities.
     - Detect numbering discontinuities.
     - Detect missing residues via comparison of SEQRES vs ATOM records.
     - Interactive selection of chains and ligands/ions to keep (e.g., zinc, cofactors).
     - Save cleaned PDB under `modules/prepared_proteins/<PDBID>/<PDBID>_cleaned.pdb`, with overwrite checks.
     - Display a small embedded 3D view (via `py3Dmol`) in browser for visual validation.
  3. **Scoring** before modeling:
     - Simple “quality” score (0–100) based on missing residues and discontinuities.
  4. **Loop modeling & structure repair**:
     - If missing residues detected:
       - **PyRosetta-based** loop modeling (KIC mover), with repeated decoy attempts:
         - Strips heteroatoms for modeling.
         - User supplies full sequence (one-letter) matching SEQRES (excluding ligands).
         - Generates a specified number of successful decoys (up to max attempts), each with:
           - Loop insertion via KIC.
           - Light relaxation (FastRelax) to relieve clashes.
           - Rosetta energy scoring.
           - Optional **Modeller DOPE** scoring (if MODELLER installed): average chain DOPE score.
           - Combined score = Rosetta energy + weight · DOPE (e.g., 0.1×DOPE).
         - Chooses best decoy by combined score.
         - Saves modeled loops PDB (`<PDBID>_cleaned_modeled.pdb`).
       - **Merging**: reinserts coordinates of modeled loops back into the cleaned PDB (to retain HETATM such as zinc), producing `<PDBID>_cleaned_merged.pdb`.
       - If fewer than requested decoys succeed, proceeds with available best.
       - Catches and logs errors (e.g., loop application failures, relax failures, DOPE scoring failures) and continues attempts.
       - If PyRosetta not available or KIC mover unavailable, falls back to manual editing prompt.
  5. **Post-modeling scoring**:
     - Re-score the merged structure against original SEQRES to report “score after modeling & merge”.
  6. **Renumbering**:
     - Interactive prompt: “Renumber residues contiguously starting at 1? [Y/n]”
     - Always uses the merged PDB when available, so final PDB is `<PDBID>_cleaned_merged_renum.pdb`.
     - Overwrite checks to avoid accidental data loss.
  7. **Final score & output**:
     - Final quality score (0–100) printed.
     - Location of final PDB shown (e.g., `modules/prepared_proteins/6A94/6A94_cleaned_merged_renum.pdb`).
- **Integration with external tools**:
  - **GROMACS**: later steps (not in this module) will rely on knowing `gmx` availability and hardware capabilities.
  - **CHARMM-GUI**: wrapper logic can open a browser instance from Python for automated upload/setup.
  - **Modeller**: if installed, DOPE scoring of Rosetta-modeled decoys is integrated.
  - **PyRosetta**: for loop modeling, relaxation, energy scoring.
- **Security & privacy**:
  - No personally identifiable information is stored.
  - System info stored locally under `~/.bpcss/system_info.json`; user can inspect or delete as needed.
- **Reproducibility**:
  - All cleaned/modeling outputs saved under versioned filenames with prompts to avoid overwrites.
  - JSON logging of system environment to detect changes over runs.

---

## 📥 Installation & Requirements

1. **Clone repository** (or install via provided `bpcss.sh` installer):
   ```bash
   git clone https://github.com/yourusername/bpcss-toolkit.git ~/.bpcss_toolkit
