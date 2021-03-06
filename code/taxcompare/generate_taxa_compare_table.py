#!/usr/bin/env python

__author__ = "Kyle Patnode"
__copyright__ = "Copyright 2012, The QIIME Project"
__credits__ = ["Kyle Patnode", "Jai Ram Rideout", "Greg Caporaso"]
__license__ = "GPL"
__version__ = "1.5.0-dev"
__maintainer__ = "Kyle Patnode"
__email__ = "kpatnode1@gmail.com"
__status__ = "Development"

from os import walk
from os.path import exists, join
from qiime.workflow.util import WorkflowError
from qiime.parse import parse_taxa_summary_table
from qiime.compare_taxa_summaries import compare_taxa_summaries

assignment_method_choices = ['rdp','blast','rtax','mothur','tax2tree','usearch','uclust']

def format_output(compare_tables, separator):
    """Formats the output from generate_taxa_compare_table into {level: [write_ready_list]}"""
    result = {}
    for key in compare_tables.iterkeys():
        result[key] = list()
        if not compare_tables[key]:
            continue
        table = compare_tables[key]
        datasets = sorted(table.keys())
        methods = set()
        for m in table.itervalues():
            #Find all methods used in table
            methods|= set(m.keys())
        methods = sorted(list(methods))
        result[key].append('P'+separator+'S\t'+'\t'.join(methods)+'\n')
        for dataset in datasets:
            line = dataset+'\t'
            for method in methods:
                try:
                    line += table[dataset][method][0] + separator + table[dataset][method][1]+'\t'
                except KeyError:
                    #Don't have data for that set/method
                    line += 'N/A'+'\t'
            result[key].append(line + '\n')
    return result

def get_key_files(directory):
    """Given a directory containing keys, will identify key files and return a dict {name of study: file path}"""
    if(not exists(directory)):
        raise WorkflowError('The key directory does not exist.')
    key_fps = {}
    for key_file in walk(directory).next()[2]:
        if (key_file.endswith('~') or key_file.endswith('.orig.txt') or
            key_file == 'README.md'):
            continue
        study = key_file.split('_')[0]
        key_fps[study] = join(directory, key_file)
    if(not key_fps):
        raise WorkflowError('There are no key files in the given directory.')
    return key_fps

def get_coefficients(run, key):
    """Given a parsed taxa summary table, will find and return correlation coefficients"""
    pearson_compare = compare_taxa_summaries(run, key, 'paired', 'pearson')
    spearman_compare = compare_taxa_summaries(run, key, 'paired', 'spearman')

    pearson_coeff = pearson_compare[2].split('\n')[-2].split()[0]
    spearman_coeff = spearman_compare[2].split('\n')[-2].split()[0]

    return pearson_coeff, spearman_coeff

def convert_taxa_summary(ts, level):
    level_data = {}
    for taxon, taxon_data in zip(ts[1], ts[2]):
        taxon_levels = taxon.split(';')

        if level > len(taxon_levels):
            raise ValueError("The requested taxonomic level %d is higher than "
                             "number of levels in the input taxa summary "
                             "file.")

        level_key = ';'.join(taxon_levels[:level])

        if level_key in level_data:
            level_data[level_key] = [sum(pair) for pair in
                                     zip(taxon_data, level_data[level_key])]
        else:
            level_data[level_key] = list(taxon_data)

    sorted_keys = sorted(level_data.keys())

    return ts[0], sorted_keys, [level_data[k] for k in sorted_keys]

def generate_taxa_compare_table(root, key_directory, levels=None):
    """Finds otu tables in root and compares them against the keys in key_directory.

    Walks a file tree starting at root and finds the otu tables output by
    multiple_assign_taxonomy.py. Then compares the found otu tables to their corresponding
    key in key_directory. Returns a dict containing another dict for every level of output
    compared. Output is of the format:
    {level: {name of study: {method_and_params: (pearson, spearman)}}}

    Parameters:
    root: path to root of multiple_assign_taxonomy.py output.
    key_directory: path to directory containing known/expected compositions. Each study
        should be in its own otu table.
    levels: INCOMPLETE. Use other than default will cause unexpected results. The
        multiple_assign_taxonomy.py output levels to be analyzed."""
    key_fps = get_key_files(key_directory)

    results = {}

    if not levels:
        levels = [2,3,4,5,6]
    if len(levels) > 5:
        raise WorkflowError('Too many levels.')
    for l in levels:
        if l < 2 or l > 6:
            raise WorkflowError('Level out of range: ' + str(l))

    for l in levels:
        results[l] = dict()

    for(path, dirs, files) in walk(root):
        for choice in assignment_method_choices:
            #Checks if this dir's name includes a known assignment method (and therefore contains that output)
            if choice in path:
                study_dir = path.split('/')[-2]
                study_keys = key_fps.keys()

                study = None
                for study_key in study_keys:
                    if study_key in study_dir:
                        study = study_key
                if study is None:
                    raise ValueError("Couldn't find matching study key for "
                                     "'%s'." % study_dir)

                for f in files:
                    if ('otu_table_mc2_no_pynast_failures_w_taxa_L' in f or
                        'otu_table_mc2_w_taxa_L' in f)\
                        and not f.endswith('~')\
                        and not f.endswith('.biom'):
                        name = path.split('/')[-2]
                        level = int(f[-5])
                        if level not in levels:
                            #If that level wasn't requested, skip it.
                            continue

                        with open(join(path,f),'U') as run_file:
                            #Open and parse run file
                            test = run_file.readline()
                            if('Taxon\t' not in test):
                                raise WorkflowError('Invalid multiple_assign_taxonomy output file, check for corrupted file: '+path)
                            run_file.seek(0)
                            run = parse_taxa_summary_table(run_file)

                        with open(key_fps[study],'U') as key_file:
                            #Open and parse key file
                            test = key_file.readline()
                            if('Taxon\t' not in test):
                                raise WorkflowError('Invalid key file in directory: '+path)
                            key_file.seek(0)
                            key = parse_taxa_summary_table(key_file)
                            key = convert_taxa_summary(key, level)

                        try:
                            pearson_coeff, spearman_coeff = get_coefficients(run, key)
                        except ValueError:
                            #compare_taxa_summaries couldn't find a match between the 2
                            #Likely due to mismatch between key and input sample names.
                            pearson_coeff = 'X'
                            spearman_coeff = 'X'
                        try:
                            results[level][name]
                        except KeyError:
                            results[level][name] = dict()
                        results[level][name][path.split('/')[-1]] = (pearson_coeff, spearman_coeff)
    return results
