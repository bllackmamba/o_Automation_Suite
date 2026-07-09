# -*- coding: utf-8 -*-
"""
Created on Sun Apr 11 14:33:07 2021

@author: Louis Beal

Tool to generate k groups for Nlist
"""

# from common import *
from increase import *
from increase import userinp as defaultprompt, safe_concat_rows, read_data as read_datas

def get_file_name(file):
    if os.path.isfile(file):
        expand = 1
        while True:
            expand += 1
            new_file_name = file.split(".xlsx")[0] +  str(expand) + ".xlsx"
            if os.path.isfile(new_file_name):
                continue
            else:
                file = new_file_name
                break
    return file

def validate_k_lists(klists, compareset):
    l = len(klists)
    for i in range(l):
        klists[i] = klists[i] & compareset
    utilised = set(itertools.chain.from_iterable(klists))
    ungrouped = compareset - utilised

    return klists, ungrouped


def format_groups(klists, datas, data, short, long, out, conformation=None):

    full = []
    head = []
    full_block_count = []
    print(len(data[0]))
    nlist = data.tolist()

    for i in range(len(klists)):
        block = list(klists[i]) + [tuple(("" for x in range(short)))]

        block_count = [len(klists[i])] + [""]*(len(block)-1)
        
        title = [list(nlist)[i]] + [tuple(("" for x in range(long)))]*(len(block)-1)
        
        full += block
        full_block_count += block_count
        head += title
    
    heads = pd.DataFrame(head)
    heads[""] = ""
    output = datas
    if conformation:
        conformation = pd.DataFrame(conformation)
        conformation[""] = ""
        output = safe_concat_rows(output, conformation)
    output = safe_concat_rows(output, heads)


    fulls = pd.DataFrame(full)
    fulls[""] = ""
    output = safe_concat_rows(output, fulls)

    fbc = pd.DataFrame(full_block_count)
    fbc[""] = ""

    output = safe_concat_rows(output, fbc)
    
    out = pd.DataFrame(out)
    out[""] = ""
    output = safe_concat_rows(output, out)

    return output

def generate_k_lists(data, num):
    all_klist = []
    for d in data:
        combos = set((tuple(sorted(x)) for x in itertools.combinations(d, num)))
        all_klist.append(combos)
    return all_klist


if __name__ == "__main__":
    
    # ---------------------------------
    #
    #    User settings below here
    # 
    # ---------------------------------
    
    userPrompt = True
    
    #target file    
    filepath = "./data/545-clip.xlsx"
    secondary = None
    reduce = 1    
    
    # ---------------------------------
    #
    #    Function calls below here
    # 
    # ---------------------------------
    # data = None
    # selected_input_id = ""
    # if userPrompt:
        # filepath = defaultprompt(filepath, valid="file")
    data, selected_input_id = read_data_from_database()

    has_conformation = defaultprompt(-1,"enter 1 if you have conformation input or any other number if you dont have: ", valid="int", show_log=False)

    if has_conformation == 1:
        # secondary = defaultprompt("","enter secondary file path: ", valid="file")
        secondary, selected_conformation_input_id = read_data_from_database(False)

    targetlen = defaultprompt(-1,"enter target length for reduction: ", valid="int")
    
    data = np.array(data)
    if targetlen < 0:
        shorts = data.shape[1] + targetlen
        
    else:
        shorts = targetlen
        
    print("grouping")
    klists = generate_k_lists(data, shorts)
    
    out = []
    for k in klists:
        for s in k:
            out.append(s)
    if not out or not klists:
        print("no combination could form a sinlge klist for the given target!!")
        print("Exiting...")
        exit()
    # print(klists)
    short = len(out[0])
    long = len(out[0])
    out = set(out)
    
    if secondary is None:
        print("outputting")
        insert_output(klists, data, [], selected_input_id, event_source="decrease")

    
    else:
        print("comparing...")
        
        compareset = set([tuple(row) for row in secondary])
        
        kvalid, ungroup = validate_k_lists(klists, compareset)
        insert_output(kvalid, data, ungroup, selected_input_id, event_source="decrease", selected_conformation_input_id=selected_conformation_input_id)

        