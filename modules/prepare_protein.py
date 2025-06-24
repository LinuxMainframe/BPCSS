#!/usr/bin/env python3
"""
Module for initial preparation of a protein PDB file for BPCSS workflow.
Features:
- Prompt user to supply a local PDB file or fetch from RCSB by PDB ID
- Parse PDB: list chains, ligands/HETATM, discontinuities in residue numbering
- Detect missing residues via SEQRES vs ATOM records
- Allow user to choose chains/ligands to keep or remove
- Renumber residues to contiguous numbering if desired
- Save cleaned PDB in per-PDB directory, with overwrite checks
- Display 3D structure using py3Dmol in browser for validation
- Score structure quality based on missing residues and discontinuities
- Handle missing residues via PyRosetta loop modeling and scoring with DOPE
"""
import os
import sys
import requests
from pathlib import Path
from Bio.PDB import PDBParser, PDBIO, Select
from collections import defaultdict
import re
import webbrowser
import shutil

# PyRosetta integration
PYRO_AVAILABLE = False
try:
    import pyrosetta
    from pyrosetta import pose_from_pdb
    from pyrosetta.rosetta.core.scoring import get_score_function
    from pyrosetta.rosetta.protocols.loops import Loops, Loop
    try:
        from pyrosetta.rosetta.protocols.loops.loop_mover.perturb import LoopMover_Perturb_KIC as KICMover
    except ImportError:
        try:
            from pyrosetta.rosetta.protocols.loops.loop_mover.refine import LoopMover_Refine_KIC as KICMover
        except ImportError:
            KICMover = None
    try:
        from pyrosetta.rosetta.core.scoring.constraints import CoordinateConstraint
    except ImportError:
        CoordinateConstraint = None
    PYRO_AVAILABLE = True
    ROSINIT = False
except ImportError:
    KICMover = None
    CoordinateConstraint = None
    ROSINIT = False

# MODELLER DOPE integration
MODELLER_AVAILABLE = False
try:
    from modeller import Environ, Selection
    from modeller.scripts import complete_pdb
    MODELLER_AVAILABLE = True
except ImportError:
    MODELLER_AVAILABLE = False

# Base toolkit directory
TOOLKIT_DIR = Path(__file__).resolve().parent
OUTPUT_BASE = TOOLKIT_DIR / 'prepared_proteins'


def init_pyrosetta():
    global ROSINIT
    if PYRO_AVAILABLE and not ROSINIT:
        pyrosetta.init(extra_options='-mute all')
        ROSINIT = True


def fetch_pdb(pdb_id, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pdb_id.upper()}.pdb"
    if out_path.exists():
        resp = input(f"{out_path} already exists. Overwrite? [y/N]: ").strip().lower()
        if resp not in ('y', 'yes'):
            print("Skipping download.")
            return out_path
    url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        with open(out_path, 'w') as f:
            f.write(resp.text)
        print(f"Downloaded PDB {pdb_id} to {out_path}")
        return out_path
    except Exception as e:
        print(f"Failed to fetch PDB {pdb_id}: {e}")
        return None


def parse_seqres(pdb_path):
    seqres = defaultdict(list)
    try:
        with open(pdb_path) as f:
            for line in f:
                if line.startswith('SEQRES'):
                    parts = line.split()
                    if len(parts) >= 4:
                        chain = parts[2]
                        residues = parts[4:]
                        seqres[chain].extend(residues)
    except Exception:
        pass
    return dict(seqres)


def parse_pdb_structure(pdb_path):
    parser = PDBParser(QUIET=True)
    try:
        struct = parser.get_structure('structure', str(pdb_path))
        return struct
    except Exception as e:
        print(f"Error parsing PDB: {e}")
        return None


def list_chains_and_hets(pdb_path):
    chains = set()
    hets = defaultdict(set)
    try:
        with open(pdb_path) as f:
            for line in f:
                record = line[:6].strip()
                if record == 'ATOM':
                    chain = line[21].strip()
                    chains.add(chain)
                elif record == 'HETATM':
                    chain = line[21].strip()
                    resname = line[17:20].strip()
                    hets[chain].add(resname)
    except Exception:
        pass
    return sorted(chains), {k: sorted(list(v)) for k, v in hets.items()}


def detect_numbering_discontinuities(structure):
    discontinuities = {}
    for model in structure:
        for chain in model:
            resseqs = [res.id[1] for res in chain]
            if not resseqs:
                continue
            jumps = []
            prev = resseqs[0]
            for curr in resseqs[1:]:
                if curr - prev != 1:
                    jumps.append((prev, curr))
                prev = curr
            if jumps:
                discontinuities[chain.id] = jumps
    return discontinuities


def detect_missing_residues(seqres_dict, structure):
    missing = {}
    for model in structure:
        for chain in model:
            cid = chain.id
            seqres = seqres_dict.get(cid)
            if not seqres:
                continue
            observed = [res.get_resname() for res in chain if res.id[0].strip() == '']
            miss = []
            i = j = 0
            while i < len(seqres) and j < len(observed):
                if seqres[i] == observed[j]:
                    i += 1; j += 1
                else:
                    miss.append((i+1, seqres[i])); i += 1
            while i < len(seqres):
                miss.append((i+1, seqres[i])); i += 1
            if miss:
                missing[cid] = miss
    return missing


def select_entities(chains, hets):
    print("Chains detected:")
    for i, c in enumerate(chains, 1): print(f"  {i}: Chain {c}")
    keep_chains = input("Enter chain numbers to keep (comma-separated), or 'all': ").strip()
    if keep_chains.lower() in ('all', ''):
        chosen_chains = chains
    else:
        nums = re.findall(r"\d+", keep_chains)
        chosen_chains = []
        for n in nums:
            idx = int(n) - 1
            if 0 <= idx < len(chains): chosen_chains.append(chains[idx])
    print(f"Keeping chains: {chosen_chains}")
    all_hets = []
    for c in chosen_chains:
        items = hets.get(c, [])
        if items:
            print(f"Chain {c} has HETATM: {items}")
            all_hets.extend([(c, h) for h in items])
    chosen_hets = []
    if all_hets:
        print("HETATM entities:")
        for i, (c, h) in enumerate(all_hets, 1): print(f"  {i}: Chain {c} - {h}")
        keep_hets = input("Enter HETATM numbers to keep (comma-separated), 'none', or 'all': ").strip()
        if keep_hets.lower() in ('none', 'n'):
            chosen_hets = []
        elif keep_hets.lower() in ('all', ''):
            chosen_hets = all_hets
        else:
            nums = re.findall(r"\d+", keep_hets)
            for n in nums:
                idx = int(n) - 1
                if 0 <= idx < len(all_hets): chosen_hets.append(all_hets[idx])
    print(f"Keeping HETATM entities: {chosen_hets}")
    return chosen_chains, chosen_hets

class CleanSelect(Select):
    def __init__(self, chains_to_keep=None, hets_to_keep=None):
        self.chains_to_keep = set(chains_to_keep or [])
        self.hets_to_keep = set(hets_to_keep or [])
    def accept_chain(self, chain): return chain.id in self.chains_to_keep
    def accept_residue(self, residue):
        hetflag, resseq, icode = residue.id
        if hetflag.strip() == '': return True
        chain = residue.get_parent().id
        resname = residue.get_resname()
        return (chain, resname) in self.hets_to_keep


def renumber_structure(structure, start=1):
    for model in structure:
        for chain in model:
            current = start
            for residue in list(chain):
                residue.id = (' ', current, ' '); current += 1
    return structure


def save_structure_with_check(structure, out_path):
    out_path = Path(out_path)
    if out_path.exists():
        resp = input(f"{out_path} exists. Overwrite? [y/N]: ").strip().lower()
        if resp not in ('y', 'yes'):
            new_name = input("Enter new filename (or leave blank to skip saving): ").strip()
            if not new_name: print("Skipping save."); return None
            out_path = out_path.with_name(new_name)
    io = PDBIO(); io.set_structure(structure); io.save(str(out_path))
    print(f"Saved PDB: {out_path}")
    return out_path


def display_3d_structure(pdb_path):
    try:
        import py3Dmol
    except ImportError:
        print("py3Dmol not installed; install via 'pip install py3Dmol' to enable 3D display.")
        return
    with open(pdb_path) as f: pdb_txt = f.read().replace('`', "'")
    html = f"""
<html>
<head>
  <script src="https://3dmol.csb.pitt.edu/build/3Dmol-min.js"></script>
</head>
<body>
<div id="viewer" style="width: 400px; height: 300px; position: relative; margin: auto;"></div>
<script>
  let viewer = $3Dmol.createViewer("viewer", {{backgroundColor: 'white'}});
  viewer.addModel(`{pdb_txt}`, "pdb");
  viewer.setStyle({{chain: ''}}, {{cartoon: {{color: 'spectrum'}}}});
  viewer.zoomTo(); viewer.render();
</script>
</body>
</html>
"""
    tmp_html = Path('/tmp') / f"view_{Path(pdb_path).stem}.html"
    with open(tmp_html, 'w') as f: f.write(html)
    webbrowser.open(f"file://{tmp_html}")
    print(f"Opened 3D view in browser: {tmp_html}")


def score_structure(seqres_dict, structure):
    total_expected=total_missing=total_jumps=0
    for model in structure:
        for chain in model:
            cid=chain.id; seqres=seqres_dict.get(cid)
            if not seqres: continue
            expected=len(seqres)
            observed=sum(1 for res in chain if res.id[0].strip()=='')
            missing=expected-observed; discontinuities=0; prev=None
            for res in chain:
                if res.id[0].strip()!='': continue
                resseq=res.id[1]
                if prev is None: prev=resseq
                else:
                    if resseq-prev!=1: discontinuities+=1
                    prev=resseq
            total_expected+=expected; total_missing+=max(missing,0); total_jumps+=discontinuities
    if total_expected==0: return 0
    score=100 - (total_missing*1) - (total_jumps*5)
    return max(0, min(100, score))


def strip_heteroatoms(input_pdb, output_pdb):
    class ProteinSelect(Select):
        def accept_residue(self, residue):
            hetflag,_,_=residue.id; return hetflag.strip()==''
    struct=parse_pdb_structure(str(input_pdb))
    if struct is None: return None
    io=PDBIO(); io.set_structure(struct); io.save(str(output_pdb), ProteinSelect())
    return output_pdb


def compute_dope_score(pdb_path):
    if not MODELLER_AVAILABLE:
        return None
    try:
        env = Environ()
        env.libs.topology.read(file='$(LIB)/top_heav.lib')
        env.libs.parameters.read(file='$(LIB)/par.lib')
        mdl = complete_pdb(env, str(pdb_path))
        total = 0.0
        count = 0
        for chain in mdl.chains:
            sel = Selection(chain)
            if hasattr(sel, 'assess_dope'):
                score = sel.assess_dope()
                total += score
                count += 1
        if count > 0:
            return total / count
        else:
            return None
    except Exception as e:
        print(f"DOPE scoring failed for {pdb_path}: {e}")
        return None


def merge_modeled_loops(cleaned_pdb, modeled_pdb, out_pdb):
    parser=PDBParser(QUIET=True)
    struct_clean=parser.get_structure('cleaned', str(cleaned_pdb))
    struct_model=parser.get_structure('modeled', str(modeled_pdb))
    for model_clean in struct_clean:
        for chain_clean in model_clean:
            cid=chain_clean.id; chain_model=None
            for model2 in struct_model:
                if cid in [c.id for c in model2]: chain_model=model2[cid]; break
            if not chain_model: continue
            for res_model in chain_model:
                res_id=res_model.id
                if res_id in chain_clean:
                    res_clean=chain_clean[res_id]
                else: continue
                for atom_model in res_model:
                    name=atom_model.get_name()
                    if name in res_clean:
                        atom_clean=res_clean[name]; atom_clean.set_coord(atom_model.get_coord())
    io=PDBIO(); io.set_structure(struct_clean); io.save(str(out_pdb))
    print(f"Merged modeled loops + heteroatoms saved to {out_pdb}")
    return out_pdb


def handle_missing_residues(structure_path, seqres_dict, cleaned_path=None):
    if not PYRO_AVAILABLE:
        print("PyRosetta not available; cannot model missing residues automatically.")
        return structure_path
    init_pyrosetta()
    print("Missing residues detected. PyRosetta-based loop modeling options:")
    print("  1) Attempt loop modeling with PyRosetta KIC")
    print("  2) Manual handling: edit externally and re-run")
    choice=input("Select option [1-2]: ").strip()
    if choice!='1':
        print("Manual editing: please edit:", structure_path); input("Press Enter when done...")
        return structure_path
    tmp_stripped=Path('/tmp')/f"{structure_path.stem}_protein_only.pdb"
    res=strip_heteroatoms(structure_path, tmp_stripped)
    if res is None:
        print("Failed to strip heteroatoms."); return structure_path
    try:
        pose=pose_from_pdb(str(tmp_stripped))
    except Exception as e:
        print("Failed to load stripped PDB into PyRosetta:", e); return structure_path
    seq_input=input("Enter full amino-acid sequence (one-letter) matching SEQRES without ligands: ").strip()
    if not seq_input:
        print("No sequence provided; aborting loop modeling."); return structure_path
    try:
        full_pose=pyrosetta.pose_from_sequence(seq_input)
    except Exception as e:
        print("Failed to create pose from sequence:", e); return structure_path
    struct_prot=parse_pdb_structure(str(tmp_stripped))
    missing=detect_missing_residues(seqres_dict, struct_prot)
    loops=Loops()
    for cid, miss_list in missing.items():
        positions=[pos for pos,_ in miss_list]; segments=[]; start=prev=None
        for pos in positions:
            if start is None: start=pos; prev=pos
            elif pos==prev+1: prev=pos
            else: segments.append((start,prev)); start=pos; prev=pos
        if start is not None: segments.append((start,prev))
        for (s,e) in segments: loops.add_loop(Loop(s,e,s))
    if KICMover is None:
        print("No KIC mover available; cannot model loops automatically."); return structure_path
    if loops.num_loop()==0:
        print("No missing segments for loop modeling."); return structure_path
    loop_mover=KICMover(loops)
    scorefxn=get_score_function()
    try:
        from pyrosetta.rosetta.protocols.relax import FastRelax
        relax_available=True
    except ImportError:
        relax_available=False
    try:
        n_decoys = int(input("Enter number of successful decoys to generate (e.g., 5): ").strip() or "5")
    except Exception:
        n_decoys = 5
    max_attempts = n_decoys * 10
    success_count = 0
    attempt = 0
    best_pose = None
    best_score = float('inf')
    print(f"Attempting to obtain {n_decoys} successful decoys (max {max_attempts})...")
    while success_count < n_decoys and attempt < max_attempts:
        attempt += 1
        print(f"Attempt {attempt} (success so far: {success_count})...")
        try:
            test_pose = full_pose.clone()
            loop_mover.apply(test_pose)
        except Exception as e:
            print(f"  Loop application failed: {e}")
            continue
        if relax_available:
            try:
                relax = FastRelax()
                relax.set_scorefxn(scorefxn)
                relax.apply(test_pose)
            except Exception as e:
                print(f"  Relax failed: {e}")
                continue
        try:
            energy = scorefxn(test_pose)
        except Exception as e:
            print(f"  Rosetta scoring failed: {e}")
            continue
        tmp_pdb = Path('/tmp') / f"decoy_{attempt}.pdb"
        try:
            test_pose.dump_pdb(str(tmp_pdb))
        except Exception as e:
            print(f"  Failed to dump PDB for DOPE: {e}")
            continue
        if MODELLER_AVAILABLE:
            dope = compute_dope_score(tmp_pdb)
        else:
            dope = None
        if dope is not None:
            combined = energy + 0.1 * dope
        else:
            combined = energy
        print(f"  Decoy {attempt}: Rosetta energy={energy:.2f}, DOPE={dope}, combined={combined:.2f}")
        success_count += 1
        if combined < best_score:
            best_score = combined
            best_pose = test_pose.clone()
    if success_count < n_decoys:
        print(f"Only {success_count} successful decoys generated (requested {n_decoys}). Proceeding with best.")
    if best_pose is None:
        print("No successful decoys; skipping automatic modeling.")
        return structure_path
    print(f"Best decoy combined score: {best_score:.2f}")
    out_modeled = structure_path.with_name(f"{structure_path.stem}_modeled.pdb")
    try:
        best_pose.dump_pdb(str(out_modeled))
        print(f"Best modeled structure saved to {out_modeled}")
    except Exception as e:
        print(f"Failed to save modeled PDB: {e}")
        return structure_path
    if cleaned_path:
        merged = structure_path.parent / f"{structure_path.stem}_merged.pdb"
        merge_modeled_loops(cleaned_path, out_modeled, merged)
        return merged
    else:
        return out_modeled

# Helper: convert PyRosetta Pose to Bio.PDB structure via temporary file
def pose_to_structure(pose):
    tmp = Path('/tmp') / 'temp_pose.pdb'
    pose.dump_pdb(str(tmp))
    return parse_pdb_structure(str(tmp))

def prepare_protein():
    choice = input("Do you have a local PDB file? [y/N]: ").strip().lower()
    if choice in ('y', 'yes'):
        path = input("Enter path to PDB file: ").strip()
        pdb_path = Path(path)
        if not pdb_path.exists():
            print("File not found.")
            return
        pdb_id = pdb_path.stem
        out_dir = OUTPUT_BASE / pdb_id
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / pdb_path.name
        if dest.exists():
            resp = input(f"{dest} exists. Overwrite? [y/N]: ").strip().lower()
            if resp in ('y', 'yes'):
                try:
                    dest.unlink()
                except:
                    pass
            else:
                pdb_path = dest
        if pdb_path != dest:
            try:
                shutil.copy(pdb_path, dest)
                pdb_path = dest
            except Exception as e:
                print(f"Failed copying file: {e}")
                return
    else:
        pdb_id = input("Enter PDB ID to fetch from RCSB: ").strip()
        out_dir = OUTPUT_BASE / pdb_id.upper()
        pdb_path = fetch_pdb(pdb_id, out_dir)
        if not pdb_path:
            return
    print(f"Working directory: {out_dir}")
    struct = parse_pdb_structure(str(pdb_path))
    if not struct:
        return
    original_seqres = parse_seqres(str(pdb_path))
    chains, hets = list_chains_and_hets(str(pdb_path))
    print(f"Chains: {chains}")
    print(f"HETATM: {hets}")
    discontinuities = detect_numbering_discontinuities(struct)
    if discontinuities:
        print("Numbering discontinuities:")
        for c, jumps in discontinuities.items():
            print(f"  Chain {c}: {jumps}")
    else:
        print("No numbering discontinuities.")
    missing = detect_missing_residues(original_seqres, struct)
    if missing:
        print("Missing residues:")
        for c, miss in missing.items():
            print(f"  Chain {c}: {len(miss)} missing")
    else:
        print("No missing residues via SEQRES.")
    chosen_chains, chosen_hets = select_entities(chains, hets)
    struct_orig = parse_pdb_structure(str(pdb_path))
    io = PDBIO()
    io.set_structure(struct_orig)
    cleaned_path = out_dir / f"{pdb_id}_cleaned.pdb"
    struct_clean = struct_orig.copy()
    io.set_structure(struct_clean)
    saved = save_structure_with_check(struct_clean, cleaned_path)
    if not saved:
        print("Cleaned PDB not saved; aborting.")
        return
    io.set_structure(parse_pdb_structure(str(pdb_path)))
    io.save(str(cleaned_path), CleanSelect(chains_to_keep=chosen_chains, hets_to_keep=chosen_hets))
    struct2 = parse_pdb_structure(str(cleaned_path))
    print("Launching 3D view...")
    display_3d_structure(cleaned_path)
    score_before = score_structure(original_seqres, struct2)
    print(f"Score before handling missing: {score_before}/100")
    if missing:
        new_path = handle_missing_residues(cleaned_path, original_seqres, cleaned_path)
        struct2 = parse_pdb_structure(str(new_path))
        score_mid = score_structure(original_seqres, struct2)
        print(f"Score after modeling & merge: {score_mid}/100")
    else:
        new_path = cleaned_path
    ren = input("Renumber residues contiguously starting at 1? [Y/n]: ").strip().lower()
    if ren in ('', 'y', 'yes'):
        struct3 = parse_pdb_structure(str(new_path))
        struct3 = renumber_structure(struct3, start=1)
        # choose output name depending on merged status
        if new_path.stem.endswith('_merged'):
            renum_name = f"{pdb_id}_cleaned_merged_renum.pdb"
        else:
            renum_name = f"{pdb_id}_cleaned_renum.pdb"
        renum_path = out_dir / renum_name
        saved2 = save_structure_with_check(struct3, renum_path)
        if saved2:
            struct_final = parse_pdb_structure(str(renum_path))
            final_path = renum_path
        else:
            struct_final = struct2
            final_path = new_path
    else:
        struct_final = struct2
        final_path = new_path
    score_after = score_structure(original_seqres, struct_final)
    print(f"Final score: {score_after}/100")
    print(f"Final PDB at {final_path}")
    return final_path

if __name__ == '__main__':
    prepare_protein()

