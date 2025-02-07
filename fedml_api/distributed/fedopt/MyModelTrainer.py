import logging

import torch
from torch import nn

import time # by yyh
import wandb #by yyh

try:
    from fedml_core.trainer.model_trainer import ModelTrainer
    from fedml_api.standalone.fedopt.optrepo import OptRepo
except ImportError:
    from FedML.fedml_core.trainer.model_trainer import ModelTrainer
    from FedML.fedml_api.standalone.fedopt.optrepo import OptRepo


class MyModelTrainer(ModelTrainer):
    
    total_epoch = 0 #by yyh
    time = time.time() #by yyh
    compute_time = 0 #new by yyh
    
    def get_model_params(self):
        return self.model.cpu().state_dict()

    def set_model_params(self, model_parameters):
        self.model.load_state_dict(model_parameters)

    def train(self, train_data, device, args):
        model = self.model

        model.to(device)
        model.train()

        criterion = nn.CrossEntropyLoss().to(device)
        opt_cls = OptRepo.name2cls(args.client_optimizer)
        optimizer = opt_cls(model.parameters(), lr=args.lr, weight_decay=args.wd)
        current_time = time.time() #new by yyh
        epoch_loss = []
        for epoch in range(args.epochs):
            batch_loss = []
            for batch_idx, (x, labels) in enumerate(train_data):
                # logging.info(images.shape)
                x, labels = x.to(device), labels.to(device)
                optimizer.zero_grad()
                log_probs = model(x)
                loss = criterion(log_probs, labels)
                loss.backward()

                if args.clip:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), args.clip)

                optimizer.step()
                batch_loss.append(loss.item())

            if len(batch_loss) > 0:
                epoch_loss.append(sum(batch_loss) / len(batch_loss))
                logging.info('(Trainer_ID {}. Local Training Epoch: {} \tLoss: {:.6f}'.format(self.id,
                                                                                              epoch,
                                                                                              sum(epoch_loss) / len(
                                                                                                  epoch_loss)))
                wandb.log({"Train/loss": sum(epoch_loss) / len(epoch_loss), "total epoch": self.total_epoch})
                
                wandb.log({"Time": time.time() - self.time, "total epoch": self.total_epoch})
                
                
        
                
            self.total_epoch += 1 
        self.compute_time += time.time() - current_time #new by yyh
        wandb.log({"Compute Time": self.compute_time, "total epoch": self.total_epoch}) #new by yyh

    def test(self, test_data, device, args):
        model = self.model

        model.eval()
        model.to(device)

        test_loss = test_acc = test_total = 0.
        criterion = nn.CrossEntropyLoss().to(device)
        with torch.no_grad():
            for batch_idx, (x, target) in enumerate(test_data):
                x = x.to(device)
                target = target.to(device)
                pred = model(x)
                loss = criterion(pred, target)
                _, predicted = torch.max(pred, 1)
                correct = predicted.eq(target).sum()

                test_acc += correct.item()
                test_loss += loss.item() * target.size(0)
                
                if len(target.size()) == 1: # 
                    test_total += target.size(0)
                elif len(target.size()) == 2: # for tasks of next word prediction
                    test_total += target.size(0) * target.size(1)

        return test_acc, test_total, test_loss
