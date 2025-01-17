import copy
import json
import math
import time
import itertools

file_path = 'test01.json'
with open(file_path) as f:
            d = json.load(f)

# weights
weights = d['weights']

alpha = weights['room_mixed_age']
beta = weights['room_nurse_skill']
gamma = weights['continuity_of_care']
delta = weights['nurse_eccessive_workload']
epsilon = weights['open_operating_theater'] #  "open_operating_theater": 20,尽量把手术都安排在一个ot里做，不然有penalty
zeta = weights['surgeon_transfer'] #  "surgeon_transfer": 1 外科医生尽量不要换手术室
eta = weights['patient_delay']
theta = weights['unscheduled_optional'] # "unscheduled_optional": 300   mandatory病人是一定要在规定期间安排的，optional也要尽量安排，不然penalty非常大
lota = 21
omega = 2

# time
# define the shift mapping 制作一个0-41的shift_mapping e.g. (0, 'early'): 0 表示第0天早班对应的shift编号是0
D = d['days'] #值为 14或28
Days = list(range(D)) #若D为14，输出结果： [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
S = list(range(3 * D)) #Shifts列表，若D=14，S = [0, 1, 2, ..., 41]
#注意！！发哥代码里data文件规定了shift从1开始，见hello打印结果，但我们的项目没有规定，所以统一从0开始
S_early = [s for s in S if int(s) % 3 == 0]  # check shift 1 morning  #遍历 S 中的每个班次 ID，将能被 3 整除的班次挑选出来。S_early = ['0', '3', '6'···'39']
S_late = [s for s in S if int(s) % 3 == 1] # S_late = ['1', '4'···'40']
S_night = [s for s in S if int(s) % 3 == 2] #S_night = ['2', '5', '8'···'41']
shift_types = d['shift_types']
shift_mapping = {}
for day in range(D): #遍历每一天，从 0 到 D-1 即0-13
        for i, shift in enumerate(shift_types): #enumerate(shift_types) 在这段代码中的作用是 同时获取班次的索引 i 和班次的名称 shift。索引 i 是用来计算 shift_id 的关键值，因此直接使用 shift_types 是不够的。
                shift_id = 3 * day + i #编码逻辑
                shift_mapping[(day, shift)] = shift_id
#print(shift_mapping) #打出来是天数对应的shift对应的转换后编号0-41.e.g.(0, 'early'): 0, (0, 'late'): 1
nurse_shift_mapping = {
    str(n['id']): [shift_mapping[(shift['day'], shift['shift'])] for shift in n['working_shifts']]
    for n in d['nurses'] # 因为nurses的json中有双层数据，所以要用两个for来解读数据。将working_shifts中的”day“和”shift“数据填到shift_mapping中就能给护士的shift一一编号
}
#print(nurse_shift_mapping) #打出来的结果是nurse id对应的所有available shift, e.g.'n00': [1, 5, 8, 11, 14, 17, 22, 26, 29, 33, 36, 41]

# rooms
rooms = {str(r['id']): r for r in d['rooms']}
R = list(rooms)# 直接从 rooms 的键生成房间 ID 列表
room_capacity = {room_id: room['capacity'] for room_id, room in rooms.items()} #room_id 是房间的 ID，例如 'r0'。room 是房间的完整信息，例如 {'id': 'r0', 'capacity': 3}

# occupants
occupants = {str(a['id']): a for a in d['occupants']}
A = list(occupants.keys())
gender = {str(a['id']): a['gender'] for a in d['occupants']}
age_group = {str(a['id']): a['age_group'] for a in d['occupants']}
age_group_mapping = {"infant": 0, "adult": 1,"elderly": 2} # 将 age_group 转换为整数0，1，2
num_age_group = {a_id: age_group_mapping[age_group[a_id]] for a_id in age_group}
length_of_stay = {str(a['id']): a['length_of_stay'] for a in d['occupants']}
workload_produced = {str(a['id']): a['workload_produced'] for a in d['occupants']}
skill_level_required = {str(a['id']): a['skill_level_required'] for a in d['occupants']}
a_room_id = {str(a['id']): a['room_id'] for a in d['occupants']}
# print(num_age_group)

# patients
patients = {str(p['id']): p for p in d['patients']}
P = list(patients.keys())
mandatory = {str(p['id']): p['mandatory'] for p in d['patients']}
gender.update ({str(p['id']): p['gender'] for p in d['patients']}) #将patients的gender字典添加到occupants的gender字典中
age_group.update ({str(p['id']): p['age_group'] for p in d['patients']})
num_age_group.update({str(p_id): age_group_mapping[age_group[p_id]] for p_id in age_group})
length_of_stay.update ({str(p['id']): p['length_of_stay'] for p in d['patients']})
surgery_release_day = {str(p['id']): p['surgery_release_day'] for p in d['patients']}
surgery_due_day = {}
for p_id in P:
     if patients[p_id]['mandatory']: # If the value is true
        surgery_due_day[p_id] = patients[p_id]['surgery_due_day']
     # else:  # If the value is false
     #    surgery_due_day[p_id] = math.inf  # Set to infinity 把due date变得无限大，也可以用scheduling period+1来表示
surgery_duration = {str(p['id']): p['surgery_duration'] for p in d['patients']}
surgeon_id = {str(p['id']): p['surgeon_id'] for p in d['patients']}
incompatible_room_ids = {str(p['id']): p['incompatible_room_ids'] for p in d['patients']}
workload_produced.update ({str(p['id']): p['workload_produced'] for p in d['patients']})
skill_level_required.update ({str(p['id']): p['skill_level_required'] for p in d['patients']})

# print(skill_level_required['p48'][1 % 3])

## Separate male and female into two lists
F = [id for id,g in gender.items() if g == 'A'] # Female
M = [id for id,g in gender.items() if g == 'B'] # Male

# surgeons
surgeons = {str(s['id']): s for s in d['surgeons']}
SG = list(surgeons.keys())
surgeon_max_load = {str(s['id']): s['max_surgery_time'] for s in d['surgeons']}
remain_surgeon_time = {
    surgeon_id1: {day: max_time for day, max_time in enumerate(surgeon_max_load[surgeon_id1])}
    for surgeon_id1 in surgeons.keys()
}
#print(remain_surgeon_time)

# OTs
operating_theaters = {str(t['id']): t for t in d['operating_theaters']} 
OT = list(operating_theaters.keys())
ot_capacity = {str(t['id']): t['availability'] for t in d['operating_theaters']}
remain_ot_time = {
    ot_id: {day: max_time for day, max_time in enumerate(ot_capacity[ot_id])}
    for ot_id in operating_theaters
}
#print(remain_ot_time)

# nurses
nurses = {str(n['id']): n for n in d['nurses']} # n for n in d这个value其实又是一个嵌套的dic
N = list(nurses.keys())
skill_level = {str(n['id']): n['skill_level'] for n in d['nurses']}
working_shifts = {str(n['id']): n['working_shifts'] for n in d['nurses']}
nurse_day = {str(n['id']): [working_shifts['day'] for working_shifts in n['working_shifts']] for n in d['nurses']} #解开json中的双层嵌套
nurse_shift = {str(n['id']): [working_shifts['shift'] for working_shifts in n['working_shifts']] for n in d['nurses']}
nurse_max_load = {str(n['id']): [working_shifts['max_load'] for working_shifts in n['working_shifts']] for n in d['nurses']}
# 初始化 nurse_max_load_mapping
nurse_max_load_mapping = {nurse_id: {s: 0 for s in S} for nurse_id in N}
# 遍历每个护士，填充对应 shift 的 max_load
for nurse_id, nurse in nurses.items():
    for shift in nurse['working_shifts']:
        day = shift['day']
        shift_type = shift['shift']
        max_load = shift['max_load']

        # 使用 shift_mapping 计算 shift_id
        shift_id = shift_mapping[(day, shift_type)]

        # 更新 nurse_max_load_mapping
        nurse_max_load_mapping[nurse_id][shift_id] = max_load
#print(nurse_max_load_mapping) #{'n00': {0: 0, 1: 5, 2: 0, 3: 0, 4: 0, 5: 15, 6: 0, 7: 0, 8: 15, 9: 0, 10: 0, 11: 15, 12: 0, 13: 0,
remain_nurse_time = {
    nurse_id: {s: max_load for s, max_load in nurse_max_load_mapping[nurse_id].items()}
    for nurse_id in N
}

# decision variables
x = {(p,r,d):0 for p in P for d in range(D) for r in R}
y = {(p,n,s):0 for p in P for n in N for s in S }
z = {(p,ot):0 for p in P for ot in OT}

# of for each day
of_day = {d: 0 for d in Days}
of1_total =0
of2_total =0
of4_total =0
of5_total =0
of6_total =0

# declaration of auxiliary variables 辅助变量的声明（这些变量用于辅助建模计算和约束条件的定义，记录分配过程中产生的各种信息。
otDayPatient = {(ot, d): set() for ot in OT for d in Days} #记录手术室 ot 在第 d 天的患者集合。
surgeonDayOT = {(sg, d): set() for sg in SG for d in Days} #记录surgeon 在第 d 天被分配到的ot集合
roomShiftNurse = {(r, s): set() for r in R for s in S}  # 记录房间 r 在班次 s 被分配的护士集合
nurseShiftRoom = {(n, s): set() for n in N for s in S}  # 记录护士 n 在班次 s 被分配到的房间集合。
active_ots = {d: set() for d in Days}  # 初始化字典，记录每一天开放的ot

# 1.1 Initialization of occupants
# 1.1.1 initiate the allocation of rooms for occupants
room_allocation = {date:{room_id: [None]* room_capacity[room_id] for room_id in R} for date in range(D)} #room_allocation[date][room_id] 初始化为一个长度为 room_capacity[room_id] 的列表，列表中的每个位置用 None 填充，表示该位置目前没有病人。
#yq：就是建立一个字典记录日期对应的room id，它的值是根据该房间床位的数量显示none的数量，如果后面该床位有人了就显示病人id
#print(room_allocation)
for a_id, room_id in a_room_id.items():
    for day in range(length_of_stay[a_id]):  # 遍历居住期间的每一天
        for i in range(room_capacity[room_id]):  # 遍历房间的每个位置
            if room_allocation[day][room_id][i] is None:  # 如果某个位置是空的
                room_allocation[day][room_id][i] = a_id   # 将 occupant ID 放入该位置
                break  # 放置成功后跳出循环
#print(room_allocation)

#此处需要初始化occupants的占用信息，如性别，年龄
## 1.1.2 initialize f_in_room and m_in_room for occupants
f_in_room = {(room_id,date): 0 for room_id in R for date in range(D)} #建立空的f in room和m in room的字典
m_in_room = {(room_id,date): 0 for room_id in R for date in range(D)}

for a_id, room_id in a_room_id.items():
    for day in range(length_of_stay[a_id]):  # 遍历居住期间的每一天
        if a_id in F:  # 如果 occupant 是女性
            f_in_room[(room_id, day)] = 1
        elif a_id in M:  # 如果 occupant 是男性
            m_in_room[(room_id, day)] = 1
#print(m_in_room)
#print(f_in_room)

## 1.1.3 initialize min & max age in rooms for occupants
age_group_min = {(r, d): math.inf for r in R for d in Days}
age_group_max = {(r, d): -math.inf for r in R for d in Days}
age_gap={(r, d): 0 for r in R for d in Days}
# 更新最大和最小年龄信息
for a_id, room_id in a_room_id.items():
    for day in range(length_of_stay[a_id]):  # 遍历该 occupant 的每一天
        if age_group_max[(room_id, day)] == -math.inf and age_group_min[(room_id, day)] == math.inf:
            # 如果房间在这一天没有记录任何年龄组，直接设置为当前 occupant 的年龄组
            age_group_max[(room_id, day)] = num_age_group[a_id]
            age_group_min[(room_id, day)] = num_age_group[a_id]
            age_gap[(room_id, day)] =age_group_max[(room_id, day)]-age_group_min[(room_id, day)]
        else:
            # 如果房间已有年龄组记录，则更新最大和最小年龄组
            age_group_max[(room_id, day)] = max(age_group_max[(room_id, day)], num_age_group[a_id])
            age_group_min[(room_id, day)] = min(age_group_min[(room_id, day)], num_age_group[a_id])
            age_gap[(room_id, day)] = age_group_max[(room_id, day)] - age_group_min[(room_id, day)]
# print(age_group_max)
# print(age_group_min)
# print(age_gap)
#1.1.4 初始化房间r每个shift的max_skill_level_required和total_workload和相应的mapping,定义prev_assigned_nurse
max_skill_level_required = {(r, s): 0 for r in R for s in S}
total_workload = {(r, s): 0 for r in R for s in S}
prev_assigned_nurse = {id: set() for id in A + P}
workload_produced_mapping = {id: {s: 0 for s in S} for id in A + P}
skill_level_required_mapping = {id: {s: 0 for s in S} for id in A + P}

# 将 occupants 的数据填入 workload_produced_mapping 和 skill_level_required_mapping
for occ_id, occ_data in occupants.items():
    workload = occ_data['workload_produced']
    occ_skill_level = occ_data['skill_level_required']

    # 将对应 shift 的数据填入字典
    for s, workload_value in enumerate(workload):
        workload_produced_mapping[occ_id][s] = workload_value
    for s, skill_value in enumerate(occ_skill_level):
        skill_level_required_mapping[occ_id][s] = skill_value
#print(workload_produced_mapping)

for d in Days:  # 遍历每一天
    for r in room_allocation[d]:  # 遍历当天的所有房间
        # 获取房间中的所有病人 ID
        patient_ids = [pid for pid in room_allocation[d][r] if pid is not None]

        for s in range(3):  # 遍历当天的 3 个 shifts
            shift = d * 3 + s  # 当前 shift 对应的索引
            if patient_ids:  # 如果房间中有病人
                # 更新 max_skill_level_required
                max_skill_level_required[(r, shift)] = max(
                    skill_level_required[pid][s] for pid in patient_ids
                )

                # 更新 total_workload
                total_workload[(r, shift)] = sum(
                    workload_produced[pid][s] for pid in patient_ids
                )

# 1.2 Patient allocation
start = time.time()
#这行代码的作用是记录当前时间（精确到秒），通常用于测量代码执行时间。 time 模块是Python 的内置模块，用于处理与时间相关的功能。
#time.time() 是该模块的一个方法。返回值：返回当前时间的时间戳（timestamp），类似于1697042345.678 表示从 1970 年到当前时间已过的秒数（包含小数部分）。后续代码可能会通过减去 start 的值来计算代码块的运行时间。
# print(start)

for d in Days:
    # print(d, time.time() - start) 每天遍历完记一下时间
    patientsToAssign = set()  # patients who need a bed on day d
    nursesToAssignEarly = set()  # nurses available in early shift
    nursesToAssignDay = set()  # nurses available in late shift
    nursesToAssignNight = set()  # nurses available in night shift

    availableRooms = [
        room_id1
        for room_id1, allocation in room_allocation[d].items()
        if None in allocation  # 检查房间是否有空位
    ]  # available rooms初始为所有房间 需要放在p的循环里重新定义，排除天容量已满的房间

    availableOTs = OT

    # 以下开始往patientsToAssign里添加病人，现在我们知道字典里的顺序不重要，因为最后还是要根据rating来确定fix谁，但是分四类筛选人很重要，因为要考虑前一天没被安排的病人
    # 前一天未被分配到房间的 mandatory 病人
    prev_day_unassigned_mandatory = [
        p for p in P
        if not any(x[(p, room, day)] for room in R for day in range(d))  # 未分配到房间
           and mandatory[p]  # 是 mandatory 病人
           and surgery_release_day[p] < d <= surgery_due_day[p]  # 手术开始日期在d之前，且手术截止日期大于当前日期
    ]

    for p in prev_day_unassigned_mandatory:
        patientsToAssign.add(p)  # 使用 set 的 add() 方法插入病人

    # 当天待分配的 mandatory 病人
    today_mandatory = [
        p for p in P if mandatory[p] and surgery_release_day[p] == d
    ]
    for p in today_mandatory:
        patientsToAssign.add(p)

    # 前一天未被分配到房间的 optional 病人，按 surgery_release_day 排序
    prev_day_unassigned_optional = [
        p for p in P
        if not any(x[(p, room, day)] for day in range(d) for room in R)  # 未分配到房间
           and not mandatory[p]  # 是 optional 病人
           and surgery_release_day[p] < d
    ]
    for p in prev_day_unassigned_optional:
        patientsToAssign.add(p)

    # 当天待分配的 optional 病人
    today_optional = [
        p for p in P if not mandatory[p] and surgery_release_day[p] == d
    ]
    for p in today_optional:
        patientsToAssign.add(p)

    # 打印病人列表
    #print(f"Day {d}, Patients to Assign: {list(patientsToAssign)}")

    # 将护士分配到不同的班次集合中
    for nurse_id, shifts in nurse_shift_mapping.items():
        if shift_mapping[(d, 'early')] in shifts:
                nursesToAssignEarly.add(nurse_id)
        if shift_mapping[(d, 'late')] in shifts:
                nursesToAssignDay.add(nurse_id)
        if shift_mapping[(d, 'night')] in shifts:
                nursesToAssignNight.add(nurse_id)

    # 打印每个班次的护士集合
    # print(f"Early shift nurses for Day {d}: {nursesToAssignEarly}")
    # print(f"Day shift nurses for Day {d}: {nursesToAssignDay}")
    # print(f"Night shift nurses for Day {d}: {nursesToAssignNight}")

    # Generate all possible nurse permutations 排列
    # one decision per day includes the assignment of three nurses (early, late and night shift)
    nurseCombinations = set(itertools.product(nursesToAssignEarly, nursesToAssignDay, nursesToAssignNight))
    #生成所有可能的护士分配组合，组合形式为 (早班护士, 白班护士, 夜班护士) itertools.product 是 Python 内置模块 itertools 提供的一个函数，
    # 用于生成输入序列的笛卡尔积。笛卡尔积将输入的多个序列中，每个序列的元素两两组合，形成所有可能的排列。set()：将生成的组合存储到集合中，确保结果中的每个组合是唯一的。
    # print(f"Nurse Combinations: {nurseCombinations}")
    # print(f"Total nurse combinations: {len(nurseCombinations)}")
    # print('Nurse Combinations ended', time.time() - start)

    # declaration of objectives
    of1 = {(p, r): 0 for p in patientsToAssign for r in availableRooms}  # "room_mixed_age": 5 年龄差异
    of2 = {(p, nc): 0 for p in patientsToAssign for nc in nurseCombinations}  # "room_nurse_skill": 1,
    of3 = {(p, nc): 0 for p in patientsToAssign for nc in nurseCombinations}  # "continuity_of_care": 1,
    of4 = {(p, nc): 0 for p in patientsToAssign for nc in nurseCombinations} #"nurse_eccessive_workload": 5
    of5 = {(p, ot): 0 for p in patientsToAssign for ot in availableOTs} #"open_operating_theater": 20
    of6 = {(p, ot): 0 for p in patientsToAssign for ot in OT}   #"surgeon_transfer": 1,
    #全局变量的SC
    of7 = {p: 0 for p in P}  #"patient_delay": 15,
    of8 = {p: 0 for p in P}  #"unscheduled_optional": 300

    # declaration of dict for expected assignment contributions 初始化患者分配评分字典
    # 为每个患者（p）、房间（r）和护士组合（nc）创建一个嵌套字典，存储分配的评分或贡献值。
    patientRatingDict = {
        p: {
            r: { # {P1:(r1,nc1):4 （r2,nc2):436 P2:（r1,nc1):43 （r2,nc2):436 P3:（r1,nc1):43 （r2,nc2):436}
                nc:{
                    ot:0
                    for ot in availableOTs
                }
                for nc in nurseCombinations
                # adaption needed if patient is not discharged between night and early shift
            }
            for r in availableRooms
        }
        for p in patientsToAssign
    }
    #print(patientRatingDict)
    # H2 p不能分到incompatible room，直接从字典里删除，免得不可行的房间也参与评分
    to_remove = set()
    for p in patientsToAssign:
        # 遍历病人的房间评分字典
        for r in list(patientRatingDict[p].keys()):  # 使用 list() 是因为我们需要修改字典
            if r in incompatible_room_ids[p]:
                # 如果房间 r 是不兼容的，删不得，不然之后rating就难办了
                for nc in nurseCombinations:
                    for ot in availableOTs:
                        patientRatingDict[p][r][nc][ot]= math.inf

    # Initialization patientRatingDict dictionary
    # 定义H1相关的辅助变量，用于记录p所对应的性别冲突的房间，方便以后遍历r的时候排除
    unavailable_room_ids = {p: [] for p in patientsToAssign}
    # 之后遍历r时，应该写：for r in [room for room in availableRooms if room not in incompatible_room_ids[p] and room not in unavailable_room_ids[p]]:

    for p in patientsToAssign:
        # H3 surgeon每天工作量限制
        #print(surgeon_id[p])
        if surgery_duration[p] > remain_surgeon_time[surgeon_id[p]][d]:
            # 如果手术时长大于医生当天的剩余时间，跳过该病人，继续下一个病人
            to_remove.add(p)
            patientRatingDict.pop(p)
            continue
        #如果surgeon有空，手术可以被安排在今天，则开始看ot
        # H4 ot容量限制
        available_ots = [
            ot_id for ot_id in OT
            if remain_ot_time[ot_id][d] >= surgery_duration[p]
        ]

        if not available_ots:  # 如果没有手术室可以容纳病人，则跳到下一个病人
            to_remove.add(p)
            patientRatingDict.pop(p)
            continue
        # 先通过otDayPatient找到当天已经有放病人的ot，优先考虑它，都没病人的话就找到剩余时间最多的手术室 best_ot = max(available_ots, key=lambda ot_id: remain_ot_time[ot_id][d])
        # 在这里，您需要更新 remain_ot_time 中该手术室当天的剩余时间 remain_ot_time[best_ot][d] -= surgery_duration

        # S5 减少每天开放的手术室数量  ot数量可能有3个比如test04，就挺烦
        for ot in OT:
            temp_otDayPatient = {(ot, d): otDayPatient[(ot, d)].copy() for ot in OT} #一定要放在ot循环里面，不然循环里的改变就会被记录用于下一次循环的计算了，但实际上这次循环之后病人并没有真的被分配到这个ot
            temp_active_ots = {d: active_ots[d].copy() for d in Days}
            # 检查当前手术室是否有足够的剩余容量
            if remain_ot_time[ot][d] >= surgery_duration[p]:
                # 模拟分配病人到手术室
                temp_otDayPatient[(ot, d)].add(p)
                # 找出当天剩余容量最大的手术室
                max_remain_ot_time_ot = max(OT, key=lambda o: remain_ot_time[o][d])
                # 统计当天有病人的手术室数量
                temp_active_ots = [
                    o for o in OT if len(temp_otDayPatient[(o, d)]) > 0
                ]
                # 记录 penalty
                of5[(p, ot)] = max(0, len(temp_active_ots))  # 手术室开放的数量即为 penalty
                # 如果当前 ot 是当天剩余容量最大的手术室
                if ot == max_remain_ot_time_ot:
                    of5[(p, ot)] -= 1
            # else:
            #     continue

            # S6 Surgeon调动
            temp_surgeonDayOT = {(sg, d): surgeonDayOT[(sg, d)].copy() for sg in SG}
            # 模拟医生分配到该手术室
            if ot not in temp_surgeonDayOT[(surgeon_id[p], d)]:
                temp_surgeonDayOT[(surgeon_id[p], d)].add(ot)
            # 计算 penalty
            of6[(p, ot)] = max(0, len(temp_surgeonDayOT[(surgeon_id[p], d)]))

        for r in [room for room in availableRooms if room not in incompatible_room_ids[p]]: # H2 incompatible room限制，288行也实现了一部分
            # H1 性别限制
            if (
                            (p in F and m_in_room[(r, d)] == 1) or
                            (p in M and f_in_room[(r, d)] == 1)
                    ):
                unavailable_room_ids[p].append(r)
                for nc in nurseCombinations:
                    for ot in availableOTs:
                        patientRatingDict[p][r][nc][ot] = math.inf
                continue

            # H7 房间容量限制体现在availableRooms中，分配完病人会自动更新

            # S1 年龄差异 room_mixed_age
            # 初始化临时变量用于计算当前分配的 age_gap 惩罚
            temp_age_group_max = 0
            temp_age_group_min = 0
            temp_age_gap = 0

            if r in room_allocation[d] and any(occupant is not None for occupant in room_allocation[d][r]):
            # 如果该房间在当前日期d已经有分配的患者（occupant != None）
                temp_age_group_max = max(age_group_max[(r, d)], num_age_group[p])
                temp_age_group_min = min(age_group_min[(r, d)], num_age_group[p])
                temp_age_gap = temp_age_group_max - temp_age_group_min
                of1[(p, r)] = temp_age_gap
            # else:
            #     continue
            #print(skill_level["n16"])
            for nc in nurseCombinations:
                nurseEarly, nurseDay, nurseNight = nc
                #print(f"nurseEarly: {nurseEarly}, nurseDay: {nurseDay}, nurseNight: {nurseNight}")

                # 是 Python 中的 解包赋值 (unpacking assignment) 操作。通过这行代码，nc 中的三个元素（即早班、白班和夜班的护士（用n in N表示））分别赋值给了 nurseEarly、nurseDay 和 nurseNight 变量。
                # nurse to shift assignment 作用就是把早中晚班的护士id和相应的shift对应起来
                init_se_values = {
                    nurseEarly: 3* int(d),  # Replace nurseEarly_se with the appropriate value
                    nurseDay: 3* int(d) + 1,  # Replace nurseDay_se with the appropriate value
                    nurseNight: 3* int(d) + 2  # Replace nurseNight_se with the appropriate value
                }
                #print(init_se_values)
                #print(skill_level["n16"])
                for nurse_type, se_value in init_se_values.items():
                    # 计算 of2
                    temp_max_skill_level_required = max(
                        max_skill_level_required[(r, se_value)],
                        skill_level_required[p][se_value % 3] #se_value % 3 是对 se_value 取模运算,相当于除以3取余数
                    )
                    #print(temp_max_skill_level_required)
                    if temp_max_skill_level_required > skill_level[nurse_type]:
                        of2[(p, nc)] += temp_max_skill_level_required - skill_level[nurse_type]

                    # 计算 of3
                    if any(existing_patient for existing_patient in room_allocation[d][r] if existing_patient): #if existing_patient是对 existing_patient 的一个条件检查，确保它不是 None，才会被提取
                        for existing_patient in room_allocation[d][r]:
                            if existing_patient and nurse_type not in prev_assigned_nurse[existing_patient]: #if existing_patient确保该值不为none，
                                #首先，nurse_type not in prev_assigned_nurse[existing_patient] 会被先计算。然后，将该结果与 existing_patient 进行 and 运算。
                                of3[(p, nc)] += 1

                    # 计算 of4
                    temp_total_workload = (
                            total_workload[(r, se_value)] +
                            workload_produced[p][se_value % 3]
                    )
                    if temp_total_workload > nurse_max_load_mapping[nurse_type][se_value]:
                        of4[(p, nc)] += temp_total_workload - nurse_max_load_mapping[nurse_type][se_value]

    # p in PatientToAssign 循环完了之后才能统一remove今天分不了的p
    patientsToAssign.difference_update(to_remove)  # 删除所有标记的元素

    # gather precalculated objectives
    for p in patientsToAssign:
        for r in [room for room in availableRooms if room not in incompatible_room_ids[p] and room not in unavailable_room_ids[p]]:
            for nc in nurseCombinations:
                for ot in availableOTs:
                    rating = (alpha * of1[(p, r)] + beta * of2[(p, nc)] + gamma * of3[(p, nc)] + delta * of4[
                    (p, nc)] + epsilon * (of5[(p, ot)]) + zeta * of6[(p, ot)] - lota * (D - surgery_due_day.get(p, D) )
                              -omega * (d-surgery_release_day.get(p, d)))
                    # omega可调整用于实现H5和H6，保证强制患者在due day之前入院
                    patientRatingDict[p][r][nc][ot] = rating
    #print(patientRatingDict)
    dcPatientsToAssign = copy.deepcopy(patientsToAssign)
    dcAvailableRooms = copy.deepcopy(availableRooms)
    dcAvailableOTs = copy.deepcopy(availableOTs)
    # 在初始化结束后，创建 patientsToAssign 和 availableRooms, availableOTs的深拷贝，用于实际分配时的操作。深拷贝保证了初始化数据的完整性，避免直接修改原始数据。
    # 深拷贝可以修改，且不会影响原对象patientsToAssign，但如果是浅拷贝的话，改了浅拷贝的值原对象也会变
    # print('Initialization ended', time.time() - start)
    # if not dcPatientsToAssign or not dcAvailableRooms or not nurseCombinations or not dcAvailableOTs:
    #     continue

    while any(dcPatientsToAssign):  # while any(dcPatientsToAssign)：表示只要仍有未分配的病人，就持续执行分配操作。
        # dcPatientsToAssign 和 dcAvailableRooms dcAvailableOTs是病人和房间和手术室的候选列表，随着分配过程会动态更新。
        # Choose the best fit and assign
        # if not dcPatientsToAssign or not dcAvailableRooms or not nurseCombinations or not dcAvailableOTs:
        #     break
        min_value = min(
            (patientRatingDict[patient][room][nurse][ot], (patient, room, nurse, ot)) for patient in dcPatientsToAssign for
            room in dcAvailableRooms for nurse in nurseCombinations for ot in dcAvailableOTs)  # min() 返回的是评分最小的那一整项元组 (评分值, 标识信息)，而不仅仅是评分值。
        # min里面生成了一个元组，第一部分是 patientRatingDict[patient][room][nurse][ot]，即对应患者、房间，护士组合和手术室的评分。
        # 第二部分是 (patient, room, nurse，ot)，包含当前的患者、房间，护士组合和手术室的标识信息。min() 会遍历生成式，选择元组中的第一部分（即评分值）最小的项。元组的比较规则：优先比较第一个元素（评分值）。如果评分值相同，则比较第二个元素（标识信息），即 (patient, room, nurse)。
        #第二部分的比较逻辑是，如果有('p1', 'r1', 'n1') 和 ('p1', 'r2', 'n1') 比较，首先比较 p1 和 p1（相等），然后比较 r1 和 r2，由于 'r1' 小于 'r2'，所以 ('p1', 'r1', 'n1') 会排在前面。
        #因此，最终返回的结果会是评分值最小且在字典顺序中最小的 (patient, room, nurse， ot) 组合
        corresponding_key = min_value[1]  # min_value[1] 是一个元组 (patient, room, nurse, ot)，包含当前最小评分值对应的患者、房间和护士组合。
        # print("Min Rating:", min_value[0]) #返回最小rating值
        # print("Corresponding Key:", corresponding_key)
        ap = corresponding_key[0]  # patient to assign 这几个值分别记录了最小rating对应的(patient, room, nurse, ot)数据
        ar = corresponding_key[1]  # room for assignment
        anc = corresponding_key[2] # nurse combination for assignment
        anE = corresponding_key[2][0]  # selected early shift nurse
        anD = corresponding_key[2][1]  # selected late shift nurse
        anN = corresponding_key[2][2]  # selected night shift nurse
        aot = corresponding_key[3] # ot for assignment
        #print(ap)
        #print(ar)
        # assign shifts to nurses
        assign_se_values = {
            anE: 3* int(d),
            anD: 3* int(d) + 1,
            anN: 3* int(d) + 2
        }
        # declaration and initialization of update relevant variables

        # Set patient-room relevant decision variables
        x[(ap, ar, d)] = 1  # patient-room assignment decision variable
        if d + length_of_stay[ap] <= D: #如果大于D有的集合就放不下了
            for day in range(d, d + length_of_stay[ap]):
                # 更新 room_allocation
                if day in room_allocation:
                    for i, bed in enumerate(room_allocation[day][ar]):
                        if bed is None:
                            room_allocation[day][ar][i] = ap
                            break  # 分配完成后立即退出循环，结果是ap被分配到ar中的一个空床位
                # 更新 f_in_room 和 m_in_room
                if ap in F:  # 女性
                    f_in_room[(ar, day)] = 1
                elif ap in M:  # 男性
                    m_in_room[(ar, day)] = 1

                # 更新 age_group_min、age_group_max、age_gap
                age_group_max[(ar, day)] = max(age_group_max[(ar, day)], num_age_group[ap])
                age_group_min[(ar, day)] = min(age_group_min[(ar, day)], num_age_group[ap])
                age_gap[(ar, day)] = age_group_max[(ar, day)] - age_group_min[(ar, day)]

                relative_day = day - d  # 住院的第几天
                # 遍历当天的所有班次
                for shift_id in range(3 * day, 3 * day + 3):
                    # 班次索引对应 0: 早班, 1: 中班, 2: 晚班
                    shift_type = shift_id % 3

                    # 计算病人在 workload_produced 和 skill_level_required 中的索引
                    data_index = 3 * relative_day + shift_type

                    # 更新 max_skill_level_required 和 total_workload
                    max_skill_level_required[(ar, shift_id)] = max(
                        max_skill_level_required[(ar, shift_id)],
                        skill_level_required[ap][data_index]
                    )
                    total_workload[(ar, shift_id)] += workload_produced[ap][data_index]

                    # 将病人 ap 的数据填入 workload_produced_mapping 和 skill_level_required_mapping
                    workload_produced_mapping[ap][shift_id] = workload_produced[ap][data_index]
                    skill_level_required_mapping[ap][shift_id] = skill_level_required[ap][data_index]
        else:
            for day in range(d, D):
                # 更新 room_allocation
                if day in room_allocation:
                    for i, bed in enumerate(room_allocation[day][ar]):
                        if bed is None:
                            room_allocation[day][ar][i] = ap
                            break  # 分配完成后立即退出循环，结果是ap被分配到ar中的一个空床位
                # 更新 f_in_room 和 m_in_room
                if ap in F:  # 女性
                    f_in_room[(ar, day)] = 1
                elif ap in M:  # 男性
                    m_in_room[(ar, day)] = 1

                # 更新 age_group_min、age_group_max、age_gap
                age_group_max[(ar, day)] = max(age_group_max[(ar, day)], num_age_group[ap])
                age_group_min[(ar, day)] = min(age_group_min[(ar, day)], num_age_group[ap])
                age_gap[(ar, day)] = age_group_max[(ar, day)] - age_group_min[(ar, day)]

                relative_day = day - d  # 住院的第几天
                # 遍历当天的所有班次
                for shift_id in range(3 * day, 3 * day + 3):
                    # 班次索引对应 0: 早班, 1: 中班, 2: 晚班
                    shift_type = shift_id % 3

                    # 计算病人在 workload_produced 和 skill_level_required 中的索引
                    data_index = 3 * relative_day + shift_type

                    # 更新 max_skill_level_required 和 total_workload
                    max_skill_level_required[(ar, shift_id)] = max(
                        max_skill_level_required[(ar, shift_id)],
                        skill_level_required[ap][data_index]
                    )
                    total_workload[(ar, shift_id)] += workload_produced[ap][data_index]

                    # 将病人 ap 的数据填入 workload_produced_mapping 和 skill_level_required_mapping
                    workload_produced_mapping[ap][shift_id] = workload_produced[ap][data_index]
                    skill_level_required_mapping[ap][shift_id] = skill_level_required[ap][data_index]

        # Set nurse-patient relevant decision variables
        for nurse_type, se_value in assign_se_values.items():  # assign_se_values见491行，是一个anE，anD,anN 分别对应shift的字典
            y[(ap, nurse_type,
               se_value)] = 1  # decision variable nurse-patient assignment 将病人 ap 分配给班次 se_value 中的护士类型 nurse_type
            # 更新 prev_assigned_nurse
            prev_assigned_nurse[ap].add(nurse_type)
            # 将当前房间分配的护士记录到 roomShiftNurse
            roomShiftNurse[(ar, se_value)].add(nurse_type)
            # 将当前护士分配到的房间记录到 nurseShiftRoom
            nurseShiftRoom[(nurse_type, se_value)].add(ar)
            #计算当前护士的剩余护理时长
            remain_nurse_time[nurse_type][se_value]-= total_workload[(ar, se_value)]


        # Set surgery planning relevant decision variables
        z[(ap,aot)] = 1 #surgery case planning decision variable
        # 更新外科医生剩余时间
        remain_surgeon_time[surgeon_id[ap]][d] -= surgery_duration[ap]
        # 更新手术室剩余时间
        #print(remain_surgeon_time)
        remain_ot_time[aot][d] -= surgery_duration[ap]
        # 在手术室的当天患者集合中加入病人
        otDayPatient[(aot, d)].add(ap)
        # 在外科医生的当天手术室集合中加入手术室
        surgeonDayOT[(surgeon_id[ap], d)].add(aot)
        # 将手术室 aot 加入到 active_ots 的第 d 天集合中
        active_ots[d].add(aot)

        # Remove assigned patient
        patientRatingDict.pop(ap) #pop 操作会删除 ap 作为键的条目，意味着该患者的信息将不再参与后续的分配或计算。
        dcPatientsToAssign.remove(ap) #dcPatientsToAssign见339行，是PatientsToAssign的深拷贝，将患者 ap 从列表中移除，表示该患者已成功分配，不再参与待分配患者的集合。
        # Remove room if it is occupied H7
        if None not in room_allocation[d][ar]:  # 如果房间已经满员
            for patient in dcPatientsToAssign:  # 遍历 dcPatientsToAssign 中的所有患者。
                del patientRatingDict[patient][
                    ar]  # 从 patientRatingDict 字典中删除与患者 patient 和房间 ar 相关的数据，也就是这种情况下对应的rating。所以即使这个rating很小之后也不会被选出来了
            dcAvailableRooms.remove(ar)  # 从 dcAvailableRooms 列表中移除房间 ar
        # print(dcAvailableRooms)

        # Update patientRatingDict 这应该是look ahead部分了，相当于ap分配完了删除了，现在开始更新ar和nc对应的rating数据了
        # Room depending updates
        # print('Start update', time.time() - start)
        to_remove = set()
        #print(patientRatingDict)
        for p in dcPatientsToAssign:
            if ar in patientRatingDict[p]:  # 如果房间ar还在的话，改变相关数据和rating
                # H1 性别限制
                if (
                        (p in F and m_in_room[(ar, d)] == 1) or
                        (p in M and f_in_room[(ar, d)] == 1)
                ):
                    unavailable_room_ids[p].append(ar)
                    for nc in nurseCombinations:
                        for ot in availableOTs:
                            patientRatingDict[p][ar][nc][ot] = math.inf

                # H2 incompatible room 在最开始已经全都解决了,相应rating已经删过了
                # H7房间容量限制，循环之前也已经删过rating和dcAvailableRooms了
                # S1 房间年龄差异，只要改变r=ar的相关rating
                for nc in patientRatingDict[p][ar]:  # 遍历 nurseCombinations
                    for ot in patientRatingDict[p][ar][nc]:  # 遍历 availableOTs
                        temp_age_group_max = max(age_group_max[(ar, d)], num_age_group[p])
                        temp_age_group_min = min(age_group_min[(ar, d)], num_age_group[p])
                        temp_age_gap = temp_age_group_max - temp_age_group_min
                        if temp_age_gap > age_gap[(ar, d)]:
                            patientRatingDict[p][ar][nc][ot] += (temp_age_gap - age_gap[(ar, d)]) * alpha  # 增加 rating 值
                    # S2,S3,S4 只改变分到ar时的护士相关罚款
                    # # 保留 patientRatingDict[p][ar][anc] 的数据
                    # anc_data = patientRatingDict[p][ar][anc]  # 暂存 anc 的数据
                    # patientRatingDict[p] = {ar: {anc: anc_data}}  # 删除其他数据并保留 anc 数据
                    # 遍历 patientRatingDict[p][ar][anc] 下的所有 ot 并增加 rating
                    if nc== anc:
                        for ot in patientRatingDict[p][ar][nc]:
                            for nurse_type, se_value in assign_se_values.items():
                                # 计算 of2 S2
                                temp_max_skill_level_required = max(
                                    max_skill_level_required[(ar, se_value)],
                                    skill_level_required_mapping[p][se_value]
                                )
                                if temp_max_skill_level_required > skill_level[nurse_type]:
                                    patientRatingDict[p][ar][anc][ot] += (temp_max_skill_level_required - skill_level[nurse_type]) * beta

                                # 计算 of3 S3
                                if any(existing_patient for existing_patient in room_allocation[d][ar] if
                                       existing_patient):  # if existing_patient是对 existing_patient 的一个条件检查，确保它不是 None，才会被提取
                                    for existing_patient in room_allocation[d][ar]:
                                        if existing_patient and nurse_type not in prev_assigned_nurse[
                                            existing_patient]:  # if existing_patient确保该值不为none，
                                            # 首先，nurse_type not in prev_assigned_nurse[existing_patient] 会被先计算。然后，将该结果与 existing_patient 进行 and 运算。
                                            patientRatingDict[p][ar][anc][ot] += 1 * gamma

                                # 计算 of4 S4
                                temp_total_workload = (
                                        total_workload[(ar, se_value)] +
                                        workload_produced_mapping[p][se_value]
                                )
                                if temp_total_workload > remain_nurse_time[nurse_type][se_value]:
                                    patientRatingDict[p][ar][anc][ot] += (temp_total_workload - remain_nurse_time[nurse_type][se_value]) * delta
                    else:
                        for ot in patientRatingDict[p][ar][nc]:
                            patientRatingDict[p][ar][nc][ot]=math.inf



            # H3 surgeon每天工作量限制
            if surgery_duration[p] > remain_surgeon_time[surgeon_id[p]][d]:
                # 如果手术时长大于医生当天的剩余时间，跳过该病人，继续下一个病人
                to_remove.add(p)
                patientRatingDict.pop(p)
                continue
            # 如果surgeon有空，手术可以被安排在今天，则开始看ot
            # H4 ot容量限制
            available_ots = [
                ot_id for ot_id in OT
                if remain_ot_time[ot_id][d] >= surgery_duration[p]
            ]

            if not available_ots:  # 如果没有手术室可以容纳病人，则跳到下一个病人
                to_remove.add(p)
                patientRatingDict.pop(p)
                continue
            # 先通过otDayPatient找到当天已经有放病人的ot，优先考虑它，都没病人的话就找到剩余时间最多的手术室 best_ot = max(available_ots, key=lambda ot_id: remain_ot_time[ot_id][d])
            # 在这里，您需要更新 remain_ot_time 中该手术室当天的剩余时间 remain_ot_time[best_ot][d] -= surgery_duration

            #print(p)
            #print(patientRatingDict)
            #删除对于该病人来说容量不足的ot的rating
            for r in [room for room in dcAvailableRooms if
                      room not in incompatible_room_ids[p] and room not in unavailable_room_ids[p]]:
                #print(r)
                for nc in nurseCombinations:
                    for ot in dcAvailableOTs:
                        if ot not in available_ots:
                            patientRatingDict[p][r][nc][ot] = math.inf

                    # S5 如果分到新的ot，增加惩罚
                    for ot in available_ots:
                        if ot not in active_ots[d]:
                            patientRatingDict[p][r][nc][ot] += 1* epsilon

                        #print(patientRatingDict)

                        # S6 Surgeon调动
                        temp_surgeonDayOT = {(sg, d): surgeonDayOT[(sg, d)].copy() for sg in SG}
                        # 模拟医生分配到该手术室
                        if ot not in temp_surgeonDayOT[(surgeon_id[p], d)]:
                            patientRatingDict[p][r][nc][ot] += 1 * zeta

        # p in PatientToAssign 循环完了之后才能统一remove今天分不了的p
        dcPatientsToAssign.difference_update(to_remove)  # 删除所有标记的元素

    #while循环结束，所有病人都分好了，此时查看还有哪些房间没有分配护士，现在分配
    roomToAssign = set(r for r in R if not roomShiftNurse[(r, 3 * d)] and
                       not roomShiftNurse[(r, 3 * d + 1)] and
                       not roomShiftNurse[(r, 3 * d + 2)])
    #print(roomToAssign)
    # 初始化房间与护士组合的成本字典
    roomNurseCost = {
        r: {nc: 0 for nc in nurseCombinations} for r in roomToAssign
    }
    # 遍历房间和护士组合，计算成本
    for r in roomToAssign:
        for nc in nurseCombinations:
            nurseEarly, nurseDay, nurseNight = nc

            # 计算各班次的 se_value
            init_se_values = {
                nurseEarly: 3 * int(d),
                nurseDay: 3 * int(d)+ 1,
                nurseNight: 3 * int(d) + 2
            }

            for nurse_type, se_value in init_se_values.items():
                # 成本部分 1: 技能不足的惩罚
                if max_skill_level_required[(r, se_value)] > skill_level[nurse_type]:
                    roomNurseCost[r][nc] += (max_skill_level_required[(r, se_value)] - skill_level[
                        nurse_type]) * beta

                # 成本部分 2: 护士是否是已有病人未分配过的
                if any(existing_patient for existing_patient in room_allocation[d][r] if existing_patient):
                    for existing_patient in room_allocation[d][r]:
                        if existing_patient and nurse_type not in prev_assigned_nurse[existing_patient]:
                            roomNurseCost[r][nc] += 1 * gamma

                # 成本部分 3: 超过护士最大负荷的惩罚
                if total_workload[(r, se_value)] > remain_nurse_time[nurse_type][se_value]:
                    roomNurseCost[r][nc] += (
                                                    total_workload[(r, se_value)] -
                                                    remain_nurse_time[nurse_type][se_value]
                                            ) * delta

    dcroomToAssign = copy.deepcopy(roomToAssign)
    # 开始分配房间直到 roomToAssign 为空
    while any(dcroomToAssign):
        # 找到最低成本的房间和护士组合
        min_value, (selected_room, selected_nc) = min(
            (roomNurseCost[r][nc], (r, nc))
            for r in roomNurseCost
            for nc in roomNurseCost[r]
        )

        # 提取选定的护士组合
        selected_nurse_early, selected_nurse_day, selected_nurse_night = selected_nc

        # 更新房间的护士分配
        roomShiftNurse[(selected_room, 3 * d)].add(selected_nurse_early)
        roomShiftNurse[(selected_room, 3 * d + 1)].add(selected_nurse_day)
        roomShiftNurse[(selected_room, 3 * d + 2)].add(selected_nurse_night)

        # 更新 prev_assigned_nurse
        for existing_patient in room_allocation[d][selected_room]:
            if existing_patient:
                prev_assigned_nurse[existing_patient].update(selected_nc)

        # 更新 remain_nurse_time 和 nurseShiftRoom
        init_se_values = {
            selected_nurse_early: 3 * int(d),
            selected_nurse_day: 3 * int(d) + 1,
            selected_nurse_night: 3 * int(d) + 2
        }
        for nurse_type, se_value in init_se_values.items():
            remain_nurse_time[nurse_type][se_value] -= total_workload[(selected_room, se_value)]
            nurseShiftRoom[(nurse_type, se_value)].add(selected_room)

        # 从未分配房间集合中移除当前房间
        roomNurseCost.pop(selected_room)
        dcroomToAssign.remove(selected_room)

    roomToAssign_update = set(r for r in R if not roomShiftNurse[(r, 3 * d)] and
                       not roomShiftNurse[(r, 3 * d + 1)] and
                       not roomShiftNurse[(r, 3 * d + 2)])
    #print(roomToAssign_update)
    #print(d)

    #计算最终cost的加总
    # declaration of objectives
    of1 = 0  # "room_mixed_age": 5 年龄差异
    of2 = 0  # "room_nurse_skill": 1,
    of4 = 0  # "nurse_eccessive_workload": 5
    of5 = 0  # "open_operating_theater": 20
    of6 = 0  # "surgeon_transfer": 1,

    # 定义每个 shift 的待分配护士集合
    shift_nurse_mapping = {
        3 * d: nursesToAssignEarly,  # 早班
        3 * d + 1: nursesToAssignDay,  # 中班
        3 * d + 2: nursesToAssignNight  # 晚班
    }

    # of1: 遍历房间，加总每个房间当天的 age gap
    # ----------------------------
    for r in R:
        # 直接从 age_gap 中读取当天房间的值
        of1 += (age_gap[(r, d)])*alpha

        # of2: 检查 s时房间的技能不足的差值
        for s in range(3*d,3*d+3):
            for nurse_id in roomShiftNurse[(r, s)]:
                if max_skill_level_required[(r, s)] > skill_level[nurse_id]:
                    of2 += (max_skill_level_required[(r, s)] - skill_level[nurse_id])*beta

    # of4: 检查每个shifts 中每个护士负责的房间总工作量是否超过她的最大工作量
    for s, nursesToAssign in shift_nurse_mapping.items():
        # 遍历该 shift 的每个护士
        for nurse_id in nursesToAssign:
            # 计算该护士在该 shift 分配的所有房间的 total_workload 之和
            total_workload_sum = sum(
                total_workload[(room, s)] for room in nurseShiftRoom[(nurse_id, s)]
            )

            # 获取该护士在该 shift 的 max_load
            max_load = nurse_max_load_mapping[nurse_id][s]

            # 如果 total_workload_sum 超过 max_load，计算超出部分
            if total_workload_sum > max_load:
                of4 += (total_workload_sum - max_load)*delta

    # of5: OT开放数量：活跃的 OT 数量
    of5 = (len(active_ots[d]))*epsilon

    # of6: Surgeon调动：加总所有 surgeon 的 OT 分配
    for sg in SG:
        of6 += (len(surgeonDayOT[(sg, d)]))*zeta

    #当天的cost加总
    of_day[d] = of1 + of2 + of4 + of5 + of6
    of1_total+=of1 # AgeMix
    of2_total+=of2 # Skill
    of4_total+=of4 # Excess
    of5_total+=of5 # OpenOT
    of6_total+=of6 # SurgeonTransfer
    # 最终目标函数值
    #print(f"of1: {of1}, of2: {of2}, of4: {of4}, of5: {of5}, of6: {of6}")
    #print(f"Day {d}: Total Cost Value = {of_day[d]}")

# 全局变量的SC
# "continuity_of_care": 1, 全局变量！
of3 = (sum(len(prev_assigned_nurse[id]) for id in A + P))*gamma  # Continuity
of7 = 0  # "patient_delay": 15,  计算延迟的天数
of8 = 0 # "unscheduled_optional": 300
for p in P:
    surgery_release_day_p = surgery_release_day[p]
    assigned_day = next((d for r in R for d in range(D) if x[(p, r, d)] == 1), None)
    #next 函数用于从可迭代对象中返回第一个满足条件的元素。如果没有符合条件的元素，则返回指定的默认值（在这里是 None）。
    # (d for r in R for d in range(D) if x[(p, r, d)] == 1)：这是一个生成器表达式，用来查找符合条件的入院日期 d。
    # 所以，这个生成器表达式会遍历所有可能的房间和日期，并返回第一个 x[(p, r, d)] == 1 的 d 值，也就是病人 p 的入院日期。
    if assigned_day is not None: #只计算该周期入院了的病人的入院延迟
        of7 += (assigned_day - surgery_release_day_p)*eta  # Delay

of8 = (sum(1 for p in P if not any(x[(p, r, d)] == 1 for r in R for d in range(D))))*theta # Unscheduled

for p in P:
    if mandatory[p]:  # 只处理 mandatory 为 True 的病人
        # 获取病人的所有入院日期（满足 x[(p, r, d)] == 1）
        if not any(x[(p, r, d)] == 1 for r in R for d in range(D)):
            print(f"强制患者没有全部入院: {p}")
        else:
            patient_admission_dates = set(
                d for r in R for d in range(D) if x[(p, r, d)] == 1
            )
            # 检查病人的入院日期是否在 surgery_release_day 和 surgery_due_day 的范围内
            if not any(surgery_release_day[p] <= d <= surgery_due_day[p] for d in patient_admission_dates):
                print(f"强制患者没有全部入院: {p}")

of_total=sum(of_day[d] for d in Days)+ of3 + of7 + of8
print(f"of1: {of1_total}, of2: {of2_total}, of3: {of3}, of4: {of4_total}, of5: {of5_total}, of6: {of6_total}, of7: {of7}, of8: {of8}")
print(f"Final Total Cost Value: {of_total}")

# Print json file as an output 定义输出数据结构
output_data = {
    "patients": [],
    "nurses": [],
    "costs": []
}

# 导出病人的入院安排
for p in P:
    for r in R:
        for d in range(D):
            if x[(p, r, d)] == 1:  # 病人p被分配到房间r的日期d
                ot_assigned = next((ot for ot in OT if z.get((p, ot), 0) == 1), None)  # 找到手术室
                output_data["patients"].append({
                    "id": p,
                    "admission_day": d,
                    "room": r,
                    "operating_theater": ot_assigned
                })
                break  # 病人只能有一个入院日期

# 导出护士的排班安排
Shifts = ["early", "late", "night"]
for n in N:
    nurse_assignments = []
    for s in S:
        day = s // 3  # 每 3 个 shift 是 1 天
        shift_name = Shifts[s % 3]  # 获取 shift 名称
        rooms_assigned = list(nurseShiftRoom.get((n, s), []))  # 护士 n 在 shift s 的房间分配
        nurse_assignments.append({
            "day": day,
            "shift": shift_name,
            "rooms": rooms_assigned
        })
    output_data["nurses"].append({
        "id": n,
        "assignments": nurse_assignments
    })

# 导出总成本和细分成本
cost_details = f"Cost: {of_total}, Unscheduled: {of8},  Delay: {of7},  OpenOT: {of5_total},  AgeMix: {of1_total},  Skill: {of2_total},  Excess: {of4_total},  Continuity: {of3},  SurgeonTransfer: {of6_total}"
output_data["costs"].append(cost_details)

# 输出到 JSON 文件
output_file = "output_schedule.json"
with open(output_file, "w") as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

print(f"排班结果已保存到 {output_file}")