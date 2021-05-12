import logging
import os
import sys

from .message_define import MyMessage
from .utils import transform_tensor_to_list

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../../")))
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../../../FedML")))
try:
    from fedml_core.distributed.communication.message import Message
    from fedml_core.distributed.server.server_manager import ServerManager
except ImportError:
    from FedML.fedml_core.distributed.communication.message import Message
    from FedML.fedml_core.distributed.server.server_manager import ServerManager

import time

class FedOptServerManager(ServerManager):
    def __init__(self, args, aggregator, comm=None, rank=0, size=0, backend="MPI", is_preprocessed=False):
        super().__init__(args, comm, rank, size, backend)
        self.args = args
        self.aggregator = aggregator
        self.round_num = args.comm_round
        self.round_idx = 0

    def run(self):
        super().run()

    def send_init_msg(self):
        # sampling clients
        client_indexes = self.aggregator.client_sampling(self.round_idx, self.args.client_num_in_total,
                                                         self.args.client_num_per_round)
        global_model_params = self.aggregator.get_global_model_params()
        for process_id in range(1, self.size):
            self.send_message_init_config(process_id, global_model_params, client_indexes[process_id - 1])

    def register_message_receive_handlers(self):
        self.register_message_receive_handler(MyMessage.MSG_TYPE_C2S_SEND_MODEL_TO_SERVER,
                                              self.handle_message_receive_model_from_client)

    def handle_message_receive_model_from_client(self, msg_params):
        sender_id = msg_params.get(MyMessage.MSG_ARG_KEY_SENDER)
        model_params = msg_params.get(MyMessage.MSG_ARG_KEY_MODEL_PARAMS)
        local_sample_number = msg_params.get(MyMessage.MSG_ARG_KEY_NUM_SAMPLES)

        self.aggregator.add_local_trained_result(sender_id - 1, model_params, local_sample_number)
        b_all_received = self.aggregator.check_whether_all_receive()
        logging.info("b_all_received = " + str(b_all_received))
        if b_all_received:
            global_model_params = self.aggregator.aggregate()
            if self.args.dataset.startswith("stackoverflow") and self.round_idx < self.round_num - 1:
                # because the testset of stackoverflow is large, we test on 10000 random samples
                self.aggregator.test_on_random_test_samples(self.round_idx, sample_num = 10000)
            else:
                self.aggregator.test_on_all_clients(self.round_idx)

            # start the next round
            self.round_idx += 1
            if self.round_idx == self.round_num:
                self.finish()
                return

            # sampling clients
            if self.is_preprocessed:
                # sampling has already been done in data preprocessor
                client_indexes = [self.round_idx] * self.args.client_num_per_round
                print('indexes of clients: ' + str(client_indexes))
            else: #for non-iid
                client_indexes = []
                for j in range(int(self.args.client_num_per_round)):
                    
                    client_indexes.append(int((int(self.round_idx) * 10 + random.randint(j*2,j*2+1)) % 1000))
                print('indexes of clients: ' + str(client_indexes))
                # # sampling clients
                #client_indexes = self.aggregator.client_sampling(self.round_idx, self.args.client_num_in_total,
                #                                                 self.args.client_num_per_round)
                
            print("size = %d" % self.size)
            if self.args.is_mobile == 1:
                print("transform_tensor_to_list")
                global_model_params = transform_tensor_to_list(global_model_params)

            for receiver_id in range(1, self.size):
                self.send_message_sync_model_to_client(receiver_id, global_model_params,
                                                       client_indexes[receiver_id - 1])

    def send_message_init_config(self, receive_id, global_model_params, client_index):
        message = Message(MyMessage.MSG_TYPE_S2C_INIT_CONFIG, self.get_sender_id(), receive_id)
        message.add_params(MyMessage.MSG_ARG_KEY_MODEL_PARAMS, global_model_params)
        message.add_params(MyMessage.MSG_ARG_KEY_CLIENT_INDEX, str(client_index))
        self.send_message(message)

    def send_message_sync_model_to_client(self, receive_id, global_model_params, client_index):
        logging.info("send_message_sync_model_to_client. receive_id = %d" % receive_id)
        start_time = time.time() #remember to import time
        message = Message(MyMessage.MSG_TYPE_S2C_SYNC_MODEL_TO_CLIENT, self.get_sender_id(), receive_id)
        message.add_params(MyMessage.MSG_ARG_KEY_MODEL_PARAMS, global_model_params)
        message.add_params(MyMessage.MSG_ARG_KEY_CLIENT_INDEX, str(client_index))
        end_time = time.time()
        logging.info("prepare message time cost: %f" % (end_time - start_time))
        start_time = time.time()
        self.send_message(message)
        end_time = time.time()
        logging.info("send message time cost: %f" % (end_time - start_time))
