#!/usr/bin/env python

"""
    This program analyzes the output of covbr output
"""
import sys
import os
import re
import argparse

ANNOTATEDSUMMARYFILE = "annotated-summary.txt"

USAGE_MSG = """

    This program is used to annotate the output generated by Bullseye's covbr program

    A summary of the annotations is written to %s
    (Previous contents, if any, are over-written)
    Note that this file will be generated in the same directory as the analyzed
    output file

    The output from covbr (i.e, the input file to this program) is similar to:

    <SNIP>/cygwin64/home/sivkumar/work/compiler-sources/trunk/<SNIP>/AliasAnalysis.cpp

    X       540  bool llvm::isIdentifiedObject(const Value *V) {
    TF      541    if (isa<AllocaInst>(V))
            542      return true;
    TF      543a   if (
      tf    543b       isa<GlobalValue>(V) &&
      -->t  543c                              !isa<GlobalAlias>(V))
            544      return true;
    TF      545    if (isNoAliasCall(V))
            546      return true;
    TF      547    if (const Argument *A = dyn_cast<Argument>(V))
      tf    548a     return A->hasNoAliasAttr() ||
      tf    548b                                   A->hasByValAttr();
            549    return false;
            550  }
    (etc)

    This script is meant to be used in conjunction with BullsEye's covbr tool.


""" % (ANNOTATEDSUMMARYFILE)


BRANCH_MSG = """\
        Total branches = %d, Branches NOT taken (F) = %d, Branches taken (T) = %d,\n\
        %%F branches = %f, %%T branches = %f
"""

INCOMPLETE_COV_FUNC_MSG = """\
        Function at line: %s has incomplete coverage
"""

NO_COV_FUNC_MSG = """\
        Function at line: %s was INVOKED but no coverage information
"""


# These are the lines that we're trying to parse:
#
# /cygwin64/home/sivkumar/work/<SNIP>include/llvm/IR/Intrinsics.gen:
# X      16776    case 'm':
# -->F   16777      if (NameR.startswith("innum.")) return Intrinsic::minnum;
# TF     16778      if (NameR.startswith("emset.")) return Intrinsic::memset;
# TF     16779      if (NameR.startswith("emmove.")) return Intrinsic::memmove;
# -->T   16780      if (NameR.startswith("emcpy.")) return Intrinsic::memcpy;
#
# Reference: http://www.bullseye.com/help/ref-covbr.html
#

FUNCOUTPUT = list()
FILEOUTPUT = list()

# Let's compile these expressions
# This is for a line of the form:
# /cygwin64/home/sivkumar/work/<SNIP>include/llvm/IR/Intrinsics.gen:
FILENAME_REGEX = re.compile('(^[/.].*?):$')

# this is for a line of the form:
# X       863a  static bool CC_X86_64_C(unsigned ValNo, MVT ValVT,

# FUNCNAME_REGEX = re.compile(r'^X\s+(\d+)\s+(.*?)\(')
FUNCNAME_REGEX = re.compile(r'^X\s+(\d+[a-z]?)\s+(.*?)(\S+)\s*\(')


# this is for lines of the form:
# -->    46374  Intrinsic::ID Intrinsic::getIntrinsicForGCCBuiltin(const <SNIP>
# -->    42036      default: llvm_unreachable("Invalid attribute number");
#

FUNCNAME_NOCOV_REGEX = re.compile(r'^-->\s+(\d+[a-z]?)\s+(.*?)\s*(\S+)\s*\(')

# this is for lines of the form:
# TF    872a   if (
#   tf  872b       LocVT == MVT::i8 ||
# tf    873        LocVT == MVT::i16) {
# -->F  875      if (ArgFlags.isSExt())
FUNCLINE_REGEX = re.compile(r'(\s*tf|TF|\s*-->[TFtf])\s+(\w+)\s*(.*)')


# Regular expression for a for statement

# FORSTMT_REGEX = re.compile(r'\s+\S+\s+for\s*\[\($]')
FORSTMT_REGEX = re.compile(r'\s+\S+\s+for\s*\(')


# function to check if a line looks like a for statement ...

def isforstatement(line):
    """ checks if this line looks like a for statement"""

    pat = FORSTMT_REGEX.search(line)
    if pat:
        return True
    else:
        return False


# Need to exclude lines similar to:
# -->    8927      if (NameR.startswith("MDGPU.trig.preop.")) <SNIP>
# returns this tuple in the case of True:
# True, function name, line number
#

def is_incomplete_coverage(line):
    """ function to check it the line is for an incomp func coverage """
    pat = FUNCNAME_NOCOV_REGEX.search(line)
    if pat and not isforstatement(line):
        if (pat.group(3) not in ["if", "while", "return"] and
                'default:' not in pat.group(2) and
                'default :' not in pat.group(2) and
                ' case ' not in pat.group(2) and
                ' return' not in pat.group(2) and
                ' if(' not in pat.group(2)):
            return (True, pat.group(3), pat.group(1))
        else:
            return (False, "", None)
    else:
        return (False, "", None)


# prints statistics for the three conditions for a branch
# three states are observed in a covbr output file:
# T -> True
# F - > False
# TF -> True and False
# For a TF state, I assume a 50-50 split
# INCOMP is a special key (used by me) for incomplete coverage

def print_func_stats(funcname, mydict, funclineno):
    """ Function to output the function annotations """
    # global FUNCOUTPUT

    if len(mydict) == 0:
        FUNCOUTPUT.append("\n\tFunction: %s\n" % (funcname, ))
        FUNCOUTPUT.append(NO_COV_FUNC_MSG % (funclineno, ))
        return

    if 'INCOMP' in mydict:
        FUNCOUTPUT.append("\n\tFunction: %s\n" % (funcname, ))
        FUNCOUTPUT.append(INCOMPLETE_COV_FUNC_MSG % (mydict['INCOMP'], ))
        return

    try:
        t_branches = len(mydict['T'])
    except KeyError:
        t_branches = 0

    try:
        tf_branches = len(mydict['TF'])
    except KeyError:
        tf_branches = 0

    try:
        f_branches = len(mydict['F'])
    except KeyError:
        f_branches = 0

    totbranches = t_branches + 2 * tf_branches + f_branches

    percentt_branches = percentf_branches = 0.0
    if totbranches > 0:
        percentt_branches = (float(t_branches + tf_branches) /
                             totbranches) * 100.0
        percentf_branches = (float(f_branches + tf_branches) /
                             totbranches) * 100.0

    FUNCOUTPUT.append("\n\tFunction: %s\n" % (funcname, ))
    FUNCOUTPUT.append(BRANCH_MSG % (totbranches, f_branches +
                                    tf_branches, t_branches + tf_branches,
                                    percentf_branches, percentt_branches))

    for k in ['F', 'T', 'TF']:
        try:
            FUNCOUTPUT.append(
                "\t\tLine numbers for branch-condition = %s are %s\n" % (
                    k, ", ".join(mydict[k])))
        except KeyError:
            pass


# this function outputs the results to the summary and
# output files
#
def output_results(fdsummaryfile, fdoutput):
    """ Function to output the results """
    global FUNCOUTPUT
    global FILEOUTPUT

    if len(FUNCOUTPUT) != 0:
        mystr = "".join(FUNCOUTPUT)
        fdoutput.write(mystr + "\n")
        fdsummaryfile.write(mystr + "\n")
        # fdsummaryfile.write("\n")
    else:
        mystr = "\tZero coverage for this file\n\n"
        fdsummaryfile.write(mystr + "\n")
        # fdsummaryfile.write("\n")

    if len(FILEOUTPUT) != 0:
        for myline in FILEOUTPUT:
            fdoutput.write("%s\n" % (myline, ))

    FUNCOUTPUT = list()
    FILEOUTPUT = list()


# function to parse and analyze the covbr output file
#
def analyze_covbr_file(fdsummaryfile, fdinput, fdoutput):

    """ Analyze the covbr output file  and generate output files """

    infile = False
    infunc = False
    infilename = ""
    funcname = ""
    mydict = dict()
    forstmt = False
    funclineno = 0

    # see description of the lines that we're trying to parse at the top
    # of this file
    for line in fdinput:
        # strip any CRLF
        line = line.rstrip()
        pat = FILENAME_REGEX.search(line)
        if pat:  # start of a file
            forstmt = False
            if funcname != "" and infile:  # prev function from prev file
                print_func_stats(funcname, mydict, funclineno)
                funcname = ""
                mydict = dict()

            if infile:
                output_results(fdsummaryfile, fdoutput)

            infilename = pat.group(1)
            infile = True
            infunc = False
            fdoutput.write("\nFile: %s\n" % (infilename, ))
            fdsummaryfile.write("\nFile: %s\n" % (infilename, ))

        elif infile:  # we're within a file now
            if forstmt:
                forstmt = False
                incomp = False
            else:
                (incomp, newfname, thislineno) = is_incomplete_coverage(line)
            if incomp:
                if funcname != "":  # previous function
                    print_func_stats(funcname, mydict, funclineno)
                    funcname = ""

                # function with incomplete coverage
                mydict = dict()
                mydict['INCOMP'] = thislineno
                print_func_stats(newfname, mydict, thislineno)
                mydict = dict()
                infunc = True  # XXX:FIXME
                funclineno = thislineno
                funcname = ""
            else:
                pat = FUNCNAME_REGEX.search(line)
                if pat:
                    # skip lines similar to:
                    # X      119410    case 4: return (Subtarget->hasSSE2());
                    if pat.group(3) == "return" or "case " in pat.group(2):
                        pass
                    else:
                        if funcname != "":  # previous function
                            print_func_stats(funcname, mydict, funclineno)
                        funclineno = pat.group(1)
                        funcname = pat.group(3)
                        infunc = True
                        mydict = dict()
                elif infunc:  # we're within a function now
                    if isforstatement(line):  # for stmt looks like a func defn
                        forstmt = True
                    else:
                        pat = FUNCLINE_REGEX.search(line)
                        if pat:
                            execcond = pat.group(1).strip(' ->').upper()
                            try:
                                mydict[execcond].append(pat.group(2))
                            except KeyError:
                                mydict[execcond] = [pat.group(2)]

        FILEOUTPUT.append(line)

    if funcname != "":
        print_func_stats(funcname, mydict, funclineno)

    output_results(fdsummaryfile, fdoutput)

    fdinput.close()
    fdsummaryfile.close()
    fdoutput.close()
    sys.stderr.write("\n\nAnnotated summary file is %s\n\n\n" % (
        ANNOTATEDSUMMARYFILE, ))


# main function

def main():
    """ main function """

    global ANNOTATEDSUMMARYFILE

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=USAGE_MSG)

    parser.add_argument('-i', '--inputfile', dest='inputfile',
                        default="",
                        required=True,
                        help='input file name (covbr output)')

    parser.add_argument('-o', '--outputfile', dest='outputfile',
                        default="",
                        required=True,
                        help='output file name (analyzed covbr output)')

    args = parser.parse_args()

    outputfile = os.path.realpath(args.outputfile)
    inputfile = os.path.realpath(args.inputfile)

    try:
        fdinput = open(inputfile, 'r')
    except IOError:
        print "Error in opening file %s" % (inputfile)
        sys.exit(1)

    if os.path.isfile(outputfile):
        print "Error, file %s already exists" % (outputfile)
        sys.exit(1)
    else:
        pathtofile = os.path.split(outputfile)[0]
        if not os.path.isdir(pathtofile):
            os.makedirs(pathtofile)
        try:
            fdoutput = open(outputfile, 'w')
        except IOError:
            print "Error in opening file %s" % (outputfile)
            sys.exit(1)

    ANNOTATEDSUMMARYFILE = pathtofile + os.path.sep + ANNOTATEDSUMMARYFILE

    try:
        fdsummaryfile = open(ANNOTATEDSUMMARYFILE, 'w')
    except IOError:
        print "Error in opening file %s" % (ANNOTATEDSUMMARYFILE)
        sys.exit(1)

    analyze_covbr_file(fdsummaryfile, fdinput, fdoutput)


if __name__ == "__main__":

    main()

