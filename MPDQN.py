import numpy as np
import random
import requests
import time
import threading
import subprocess
import json
import statistics
import os
import datetime
import math
from pdqn_v1 import PDQNAgent
from pdqn_multipass import MultiPassPDQNAgent

print(datetime.datetime.now())

# request rate r
data_rate = 20    # if not use_tm
use_tm = 1  # if use_tm
tm_path = 'request/request15.txt'  # traffic path
# Warning !!!need to modify pdqn_v1.py loss_result_dir also
result_dir = "./pdqn_result/result3/evaluate2/"
## initial
request_num = []
# timestamp    :  0, 1, 2, , ..., 61, ..., 3601
# learning step:   0,  ..., 1,     , 120

simulation_time = 3600  #
request_n = simulation_time + 60  # for last step

## global variable
change = 0   # 1 if take action / 0 if init or after taking action
reset_complete = 0
send_finish = 0
timestamp = 0  # plus 1 in funcntion : send_request
RFID = 0  # oneM2M resource name  (Need different)
event_mn1 = threading.Event()
event_mn2 = threading.Event()
event_timestamp_Ccontrol = threading.Event()
event_monitor = threading.Event()

# Need modify ip if ip change
ip = "192.168.99.128"  # app_mn1
ip1 = "192.168.99.129"  # app_mn2


# Parameter
w_pref = 0.8
w_res = 0.2
error_rate = 0.2  # 0.2/0.5
Tmax_mn1 = 20
Tmax_mn2 = 20
Tupper = 50

## Learning parameter
# S ={k, u , c, r} {k, u , c}
# k (replica): 1 ~ 3                          actual value : same
# u (cpu utilization) : 0.0, 0.1 0.2 ...1     actual value : 0 ~ 100
# c (used cpus) : 0.1 0.2 ... 1               actual value : same

total_episodes = 16   # Training_episodes

if_test = True
if if_test:
    total_episodes = 1  # Testing_episodes
monitor_period = 60
multipass = True  # False : PDQN  / Ture: MPDQN

# Exploration parameters
epsilon_steps = 60  # episode per step
epsilon_initial = 1   #
epsilon_final = 0.01  # 0.01

# Learning rate
tau_actor_param = 0.001 # 0.01
tau_actor = 0.01  # 0.1

learning_rate_actor_param = 0.001
learning_rate_actor = 0.01
gamma = 0.9                 # Discounting rate
replay_memory_size = 960  # Replay memory
batch_size = 16
initial_memory_threshold = 16  # Number of transitions required to start learning
use_ornstein_noise = False
layers = [64,]
seed = 7

clip_grad = 0  # no use now
action_input_layer = 0  # no use now
# cres_norml = False
if not if_test:
    # check result directory
    if os.path.exists(result_dir):
        print("Deleting existing result directory...")
        raise SystemExit  # end process

    # build dir
    os.mkdir(result_dir)
# store setting
path = result_dir + "setting.txt"

# Define settings dictionary
settings = {
    'date': datetime.datetime.now(),
    'data_rate': data_rate,
    'use_tm': use_tm,
    'Tmax_mn1': Tmax_mn1,
    'Tmax_mn2': Tmax_mn2,
    'simulation_time': simulation_time,
    'tau_actor': tau_actor,
    'tau_actor_param': tau_actor_param,
    'learning_rate_actor': learning_rate_actor,
    'learning_rate_actor_param': learning_rate_actor_param,
    'gamma': gamma,
    'epsilon_steps': epsilon_steps,
    'epsilon_final': epsilon_final,
    'replay_memory_size': replay_memory_size,
    'batch_size': batch_size,
    'loss_function': 'MSE loss',
    'layers': layers,
    'if_test': if_test,
    'w_pref': w_pref,
    'w_res': w_res,
}


# Write settings to file
with open(result_dir + 'setting.txt', 'a') as f:
    for key, value in settings.items():
        f.write(f'{key}: {value}\n')


## 8 sensors
sensors = ["RFID_Container_for_stage0", "RFID_Container_for_stage1", "Liquid_Level_Container", "RFID_Container_for_stage2",
         "Color_Container", "RFID_Container_for_stage3", "Contrast_Data_Container", "RFID_Container_for_stage4"]

if use_tm:
    f = open(tm_path)

    for line in f:
        if len(request_num) < request_n:

            request_num.append(int(float(line)))
else:
    request_num = [data_rate for i in range(request_n)]

print("request_num:: ", len(request_num), "simulation_time:: ", simulation_time)


class Env:

    def __init__(self, service_name):

        self.service_name = service_name
        self.cpus = 1
        self.replica = 1
        self.cpu_utilization = 0.0
        self.action_space = ['1', '1', '1']
        self.state_space = [1, 0, 0.5, 20]
        self.n_state = len(self.state_space)
        self.n_actions = len(self.action_space)

        # Need modify ip if container name change
        self.url_list = ["http://" + ip + ":666/~/mn-cse/mn-name/AE1/RFID_Container_for_stage4",
                                    "http://" + ip1 + ":777/~/mn-cse/mn-name/AE2/Control_Command_Container",
                                    "http://" + ip + ":1111/test", "http://" + ip1 + ":2222/test"]

    def reset(self):
        self.replica = 1
        self.cpus = 1
        # if self.service_name == 'app_mn2':
        #     self.replica = 1
        #     self.cpus = 0.85

        self.state_space[0] = self.replica
        self.state_space[2] = self.cpus

        return self.state_space
    def get_response_time(self):

        path1 = result_dir + self.service_name + "_response.txt"
        f1 = open(path1, 'a')
        RFID = random.randint(0, 1000000)
        headers = {"X-M2M-Origin": "admin:admin", "Content-Type": "application/json;ty=4"}
        data = {
            "m2m:cin": {
                "con": "true",
                "cnf": "application/json",
                "lbl": "req",
                "rn": str(RFID + 1000),
            }
        }
        # URL
        service_name_list = ["app_mn1", "app_mn2"]
        url = self.url_list[service_name_list.index(self.service_name)]
        try:
            start = time.time()
            response = requests.post(url, headers=headers, json=data, timeout=0.05)
            response = response.status_code
            end = time.time()
            response_time = end - start
        except requests.exceptions.Timeout:
            response = "timeout"
            response_time = 0.05

        data1 = str(timestamp) + ' ' + str(response) + ' ' + str(response_time) + ' ' + str(self.cpus) + ' ' + str(self.replica) + '\n'
        f1.write(data1)
        f1.close()
        if str(response) != '201':
            response_time = 0.05

        return response_time

    def get_cpu_utilization(self):
        if self.service_name =='app_mn1':
            worker_name = 'worker'
        else:
            worker_name = 'worker1'
        cmd = "sudo docker-machine ssh " + worker_name + " docker stats --all --no-stream --format \\\"{{ json . }}\\\" "
        returned_text = subprocess.check_output(cmd, shell=True)
        my_data = returned_text.decode('utf8')
        my_data = my_data.split("}")
        cpu_list = []
        for i in range(len(my_data) - 1):
            # print(my_data[i]+"}")
            my_json = json.loads(my_data[i] + "}")
            name = my_json['Name'].split(".")[0]
            cpu = my_json['CPUPerc'].split("%")[0]
            if float(cpu) > 0 and (name == self.service_name):
                cpu_list.append(float(cpu))
        avg_replica_cpu_utilization = sum(cpu_list)/len(cpu_list)
        return avg_replica_cpu_utilization

    def get_cpu_utilization_from_data(self):
        path = result_dir + self.service_name + '_cpu.txt'
        try:
            f = open(path, "r")
            cpu = []
            time = []
            for line in f:
                s = line.split(' ')
                time.append(float(s[0]))
                cpu.append(float(s[1]))

            last_avg_cpu = statistics.mean(cpu[-5:])
            f.close()
        except:
            print('cant open')
        return last_avg_cpu

    def discretize_cpu_value(self, value):
        return int(round(value / 10))

    def step(self, action, event, done):
        global timestamp, send_finish, change, simulation_time


        action_replica = action[0]
        action_cpus = action[1][action_replica][0]
        # if self.service_name == 'app_mn2':
        #     action_replica = 0  # replica  = 3
        #     action_cpus = 0.9
        self.replica = action_replica + 1  # 0 1 2 (index)-> 1 2 3 (replica)
        self.cpus = round(action_cpus, 2)
        # restart
        cmd = "sudo docker-machine ssh default docker service update --replicas 0 " + self.service_name
        returned_text = subprocess.check_output(cmd, shell=True)
        # do agent action
        cmd1 = "sudo docker-machine ssh default docker service scale " + self.service_name + "=" + str(self.replica)
        cmd2 = "sudo docker-machine ssh default docker service update --limit-cpu " + str(self.cpus) + " " + self.service_name
        returned_text = subprocess.check_output(cmd1, shell=True)
        returned_text = subprocess.check_output(cmd2, shell=True)

        time.sleep(30)  # wait service start

        event.set()

        time.sleep(55)  # wait for monitor ture value
        # event_monitor.wait()

        response_time_list = []
        # self.cpu_utilization = self.get_cpu_utilization()
        self.cpu_utilization = self.get_cpu_utilization_from_data()

        for i in range(5):
            time.sleep(1)
            response_time_list.append(self.get_response_time())
        mean_response_time = statistics.mean(response_time_list)
        mean_response_time = mean_response_time*1000  # 0.05s -> 50ms

        t_max = 0  # for initial
        if self.service_name == "app_mn1":
            t_max = Tmax_mn1
        elif self.service_name == "app_mn2":
            t_max = Tmax_mn2

        Rt = mean_response_time
        # Cost 1
        # B = 10
        # if Rt > t_max:
        #     c_perf = 1
        # else:
        #     tmp_d = B * (Rt - t_max) / t_max
        #     c_perf = math.exp(tmp_d)

        # Cost 2
        B = 10
        target = t_max + 2 * math.log(0.9)
        c_perf = np.where(Rt <= target, np.exp(B * (Rt - t_max) / t_max), 0.9 + ((Rt - target) / (Tupper - target)) * 0.1)

        c_res = (self.replica*self.cpus)/3   # replica*self.cpus / Kmax
        next_state = []
        # # k, u, c # r

        # u = self.discretize_cpu_value(self.cpu_utilization)
        next_state.append(self.replica)
        next_state.append(self.cpu_utilization/100/self.cpus)
        next_state.append(self.cpus)
        next_state.append(Rt)
        # next_state.append(request_num[timestamp])

        # normalize
        # c_perf = 0 + ((c_perf - math.exp(-Tupper/t_max)) / (1 - math.exp(-Tupper/t_max))) * (1 - 0)  # min max normalize
        # c_res = 0 + ((c_res - (1 / 6)) / (1 - (1 / 6))) * (1 - 0)  # min max normalize
        reward_perf = w_pref * c_perf
        reward_res = w_res * c_res
        reward = -(reward_perf + reward_res)
        return next_state, reward, reward_perf, reward_res



def store_cpu(worker_name):
    global timestamp, cpus, change, reset_complete

    cmd = "sudo docker-machine ssh " + worker_name + " docker stats --no-stream --format \\\"{{ json . }}\\\" "
    while True:

        if send_finish == 1:
            break
        if change == 0 and reset_complete == 1:
            returned_text = subprocess.check_output(cmd, shell=True)
            my_data = returned_text.decode('utf8')
            # print(my_data.find("CPUPerc"))
            my_data = my_data.split("}")
            # state_u = []
            for i in range(len(my_data) - 1):
                # print(my_data[i]+"}")
                my_json = json.loads(my_data[i] + "}")
                name = my_json['Name'].split(".")[0]
                cpu = my_json['CPUPerc'].split("%")[0]
                if float(cpu) > 0:
                    path = result_dir + name + "_cpu.txt"
                    f = open(path, 'a')
                    data = str(timestamp) + ' '
                    data = data + str(cpu) + ' ' + '\n'

                    f.write(data)
                    f.close()


# reset Environment
# replicas = 1
# limit-cpu 1
def reset():
    cmd1 = "sudo docker-machine ssh default docker service update --replicas 1 app_mn1 "
    cmd2 = "sudo docker-machine ssh default docker service update --replicas 1 app_mn2 "
    cmd3 = "sudo docker-machine ssh default docker service update --limit-cpu 1 app_mn1"
    cmd4 = "sudo docker-machine ssh default docker service update --limit-cpu 1 app_mn2"
    subprocess.check_output(cmd1, shell=True)
    subprocess.check_output(cmd2, shell=True)
    subprocess.check_output(cmd3, shell=True)
    subprocess.check_output(cmd4, shell=True)


def store_reward(service_name, reward):
    # Write the string to a text file
    path = result_dir + service_name + "_reward.txt"
    f = open(path, 'a')
    data = str(reward) + '\n'
    f.write(data)



def store_trajectory(service_name, step, s, a_r, a_c, r, r_perf, r_res, s_, done, if_epsilon):
    path = result_dir + service_name + "_trajectory.txt"
    tmp_s = list(s)
    tmp_s_ = list(s_)
    a_c_ = list(a_c)
    f = open(path, 'a')
    data = str(step) + ' ' + str(tmp_s) + ' ' + str(a_r) + ' ' + str(a_c_) + ' ' + str(r) + ' ' + str(r_perf) + ' ' + str(r_res) + ' ' + str(tmp_s_) + ' ' + str(done) + ' ' + str(if_epsilon) + '\n'
    f.write(data)


def store_error_count(error):
    # Write the string to a text file
    path = result_dir + "error.txt"
    f = open(path, 'a')
    data = str(error) + '\n'
    f.write(data)



def post_url(url, RFID):
    if error_rate > random.random():
        content = "false"
    else:
        content = "true"
    headers = {"X-M2M-Origin": "admin:admin", "Content-Type": "application/json;ty=4"}
    data = {
        "m2m:cin": {
            "con": content,
            "cnf": "application/json",
            "lbl": "req",
            "rn": str(RFID),
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=0.05)
        response = str(response.status_code)
    except requests.exceptions.Timeout:
        response = "timeout"

    # return response

def send_request(sensors, request_num, total_episodes):
    global change, send_finish, reset_complete
    global timestamp, use_tm, RFID
    error = 0
    # event_monitor.clear()
    for episode in range(total_episodes):
        timestamp = 0
        print("episode: ", episode+1)
        print("reset envronment")
        reset_complete = 0
        reset()  # reset Environment
        time.sleep(70)
        print("reset envronment complete")
        reset_complete = 1
        send_finish = 0
        for i in request_num:
            # print('timestamp: ', timestamp)
            event_mn1.clear()  # set flag to false
            event_mn2.clear()
            # if ((timestamp + 6) % monitor_period == 0):
            #     event_monitor.set()
            # event_monitor.clear()
            if ((timestamp) % 60) == 0 and timestamp!=0 :  # every 60s scaling
                print("wait mn1 mn2 step and service scaling ...")
                event_mn1.wait()  # if flag == false : wait, else if flag == True: continue
                event_mn2.wait()
                change = 0
            event_timestamp_Ccontrol.clear()
            # exp = np.random.exponential(scale=1 / i, size=i)
            tmp_count = 0
            for j in range(i):
                try:
                    url = "http://" + ip + ":666/~/mn-cse/mn-name/AE1/"
                    # change sensor
                    url1 = url + sensors[(tmp_count * 10 + j) % 8]
                    post_url(url1, RFID)
                    RFID += 1  # oneM2M resource name  # Plus 1 for different resource name

                except:
                    print("error")
                    error += 1

                time.sleep(1 / i)
                tmp_count += 1
            timestamp += 1
            event_timestamp_Ccontrol.set()

    send_finish = 1

    store_error_count(error)



def pad_action(act, act_param):
    params = [np.zeros((1,), dtype=np.float32), np.zeros((1,), dtype=np.float32), np.zeros((1,), dtype=np.float32)]
    params[act][:] = act_param
    return (act, params)


def mpdqn(total_episodes, batch_size, gamma, initial_memory_threshold,
        replay_memory_size, epsilon_steps, tau_actor, tau_actor_param, use_ornstein_noise, learning_rate_actor,
        learning_rate_actor_param, epsilon_final,
        clip_grad, layers, multipass, action_input_layer, event, service_name, seed):
    global timestamp, simulation_time

    env = Env(service_name)


    agent_class = PDQNAgent
    if multipass:
        agent_class = MultiPassPDQNAgent
    agent = agent_class(
                       env.n_state, env.n_actions,
                       batch_size=batch_size,
                       learning_rate_actor=learning_rate_actor,
                       learning_rate_actor_param=learning_rate_actor_param,
                       epsilon_initial=epsilon_initial,
                       epsilon_steps=epsilon_steps,
                       gamma=gamma,
                       tau_actor=tau_actor,
                       tau_actor_param=tau_actor_param,
                       clip_grad=clip_grad,
                       initial_memory_threshold=initial_memory_threshold,
                       use_ornstein_noise=use_ornstein_noise,
                       replay_memory_size=replay_memory_size,
                       epsilon_final=epsilon_final,
                       actor_kwargs={'hidden_layers': layers,
                                     'action_input_layer': action_input_layer},
                       actor_param_kwargs={'hidden_layers': layers,
                                           'squashing_function': True,
                                           'output_layer_init_std': 0.0001},
                       seed=seed,
                       service_name=service_name)
    # print(agent)

    # init_state = [1, 1.0, 0.5, 20]  # replica / cpu utiliation / cpus / response time
    step = 1
    for episode in range(1, total_episodes+1):
        if if_test:  # Test
            agent.load_models(result_dir + env.service_name + "_" + str(seed))
            agent.epsilon_final = 0.
            agent.epsilon = 0.
            agent.noise = None

        state = env.reset()  # replica / cpu utiliation / cpus / response time

        done = False

        while True:
            print(timestamp)
            if timestamp == 55:
                # state[1] = (env.get_cpu_utilization() / 100 / env.cpus)
                state[1] = (env.get_cpu_utilization_from_data() / 100 / env.cpus)
                response_time_list = []
                for i in range(5):
                    time.sleep(1)
                    response_time_list.append(env.get_response_time())
                mean_response_time = statistics.mean(response_time_list)
                mean_response_time = mean_response_time * 1000
                Rt = mean_response_time
                state[3] = Rt
                break
        state = np.array(state, dtype=np.float32)
        print("service name:", env.service_name, "initial state:", state)
        print("service name:", env.service_name, " episode:", episode)
        act, act_param, all_action_parameters, if_epsilon = agent.act(state)

        action = pad_action(act, act_param)

        while True:
            if timestamp == 0:
                done = False
            event_timestamp_Ccontrol.wait()

            if (((timestamp) % 60) == 0) and (not done) and timestamp!=0:
                if timestamp == (simulation_time):
                    done = True
                else:
                    done = False

                next_state, reward, reward_perf, reward_res = env.step(action, event, done)
                # print("service name:", env.service_name, "action: ", action[0] + 1, round(action[1][action[0]][0], 2))

                # Covert np.float32
                next_state = np.array(next_state, dtype=np.float32)
                next_act, next_act_param, next_all_action_parameters, if_epsilon = agent.act(next_state)

                print("service name:", env.service_name, "action: ", act + 1, act_param, all_action_parameters, " step: ", step,
                      " next_state: ",
                      next_state, " reward: ", reward, " done: ", done, "epsilon", agent.epsilon)
                store_trajectory(env.service_name, step, state, act + 1, all_action_parameters, reward, reward_perf,
                                 reward_res,
                                 next_state, done, if_epsilon)
                next_action = pad_action(next_act, next_act_param)
                if not if_test:
                    agent.step(state, (act, all_action_parameters), reward, next_state,
                               (next_act, next_all_action_parameters), done)
                act, act_param, all_action_parameters = next_act, next_act_param, next_all_action_parameters

                action = next_action
                state = next_state
                if not if_test:
                    agent.epsilon_decay()

                step += 1
                event_timestamp_Ccontrol.clear()
                if done:
                    break
    if not if_test:
        agent.save_models(result_dir + env.service_name + "_" + str(seed))
    # end_time = time.time()
    # print(end_time-start_time)




t1 = threading.Thread(target=send_request, args=(sensors, request_num, total_episodes, ))
t2 = threading.Thread(target=store_cpu, args=('worker',))
t3 = threading.Thread(target=store_cpu, args=('worker1',))
t4 = threading.Thread(target=mpdqn, args=(total_episodes, batch_size, gamma, initial_memory_threshold,
        replay_memory_size, epsilon_steps, tau_actor, tau_actor_param, use_ornstein_noise, learning_rate_actor,
        learning_rate_actor_param, epsilon_final,
        clip_grad, layers, multipass, action_input_layer, event_mn1, 'app_mn1', seed, ))

t5 = threading.Thread(target=mpdqn, args=(total_episodes, batch_size, gamma, initial_memory_threshold,
        replay_memory_size, epsilon_steps, tau_actor, tau_actor_param, use_ornstein_noise, learning_rate_actor,
        learning_rate_actor_param, epsilon_final,
        clip_grad, layers, multipass, action_input_layer, event_mn2, 'app_mn2', seed, ))

t1.start()
t2.start()
t3.start()
t4.start()
t5.start()


t1.join()
t2.join()
t3.join()
t4.join()
t5.join()

