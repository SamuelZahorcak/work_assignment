import redis
import pickle
from time import sleep, time


class TestFsm():
    # states: 1 - idle, 2 - alert, 3 - recovery
    def __init__(self):
        self.current_state = 1
        self.state_switch_timestamp = time()
        self.over_50_timestamp = time()
        self.over_100_timestamp = time()
        self.over_50_flag = False  # flags to check whether threshold timestamps are active
        self.over_100_flag = False

    def switch_idle_to_alert(self, current_time):
        self.current_state = 2
        self.state_switch_timestamp = current_time
        # deactivate threshold crossing timestamps, since we are leaving idle state
        self.over_50_flag = False
        self.over_100_flag = False

    def process_one(self, delta_f, duration_50, duration_100, duration_recovery):
        current_time = time()

        match self.current_state:

            case 1:  # idle current state

                # 50 switch rule
                if self.over_50_flag & (abs(delta_f) >= 50) & (current_time - self.over_50_timestamp >= float(duration_50)):
                    self.switch_idle_to_alert(current_time)

                # 100 switch rule
                elif self.over_100_flag & (abs(delta_f) >= 100) & (current_time - self.over_100_timestamp >= float(duration_100)):
                    self.switch_idle_to_alert(current_time)

                # 200 switch rule
                elif abs(delta_f) >= 200:
                    self.switch_idle_to_alert(current_time)

                # check threshold crossing
                elif abs(delta_f) >= 50:

                    # activate and update threshold crossing timestamps if inactive
                    if ~self.over_50_flag:
                        self.over_50_timestamp = current_time
                        self.over_50_flag = True

                    if ~self.over_100_flag & (abs(delta_f) >= 100):
                        self.over_100_timestamp = current_time
                        self.over_100_flag = True

                    # deactivate over_100 if delta_f fell below 100 but not below 50
                    elif self.over_100_flag & (abs(delta_f) <= 100):
                        self.over_100_flag = False

                # no threshold crossed, deactivate crossing timestamps
                else:
                    self.over_50_flag = False
                    self.over_100_flag = False

            case 2:  # alert current state

                # return to idle state
                if abs(delta_f) < 50:
                    self.current_state = 1
                    self.state_switch_timestamp = current_time

                # switch to recovery state
                elif current_time - self.state_switch_timestamp >= float(duration_recovery):
                    self.current_state = 3
                    self.state_switch_timestamp = current_time

            case 3:  # recovery current state

                if current_time - self.state_switch_timestamp >= float(duration_recovery):
                    self.current_state = 1
                    self.state_switch_timestamp = current_time

        return self.current_state


# configuration
input_name = 'device'   # redis hash name
input_keys = ['frequency', 'duration_50mHz', 'duration_100mHz',
              'duration_recovery']    # redis hash fields
host_ip = 'redis-db'
host_port = 6379
sampling_time = 2   # seconds
output_name = 'current_state'
output_key = 'state_number'

# initialization
try:
    with open('data/stored_fsm.pkl', 'rb') as file:
        fsm = pickle.load(file)

    if ~isinstance(fsm, TestFsm):
        raise TypeError('Loaded FSM is not of correct type')

except:
    fsm = TestFsm()

r = redis.Redis(host=host_ip, port=host_port, decode_responses=True)
init_flag = True

# work loop
while True:

    try:
        f_new, dur_50, dur_100, dur_rec = r.hmget(input_name, input_keys)

    except:
        print('Unable to retrieve data from Redis')

    else:

        # first iteration will set delta_f to zero, may be undesirable when restarting app from an alert state
        if init_flag:
            f_old = f_new
            init_flag = False

        delta_f = float(f_new) - float(f_old)

        state = fsm.process_one(delta_f, int(
            dur_50), int(dur_100), int(dur_rec))

        try:
            r.hset(name=output_name, key=output_key, value=state)

        except:
            print('Unable to upload state to Redis')

        try:
            with open('data/stored_fsm.pkl', 'wb') as file:
                pickle.dump(fsm, file)

        except:
            print('Unable to pickle FSM')

        f_old = f_new

    sleep(sampling_time)
