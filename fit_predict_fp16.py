from __future__ import absolute_import

import argparse
import collections
import os
from datetime import datetime

import cv2
import numpy as np
import torch
from apex import amp
from catalyst.dl.callbacks import UtilsFactory
from catalyst.dl.experiments import SupervisedRunner
from pytorch_toolbelt.utils import fs
from pytorch_toolbelt.utils.catalyst_utils import ShowPolarBatchesCallback, EpochJaccardMetric, PixelAccuracyMetric
from pytorch_toolbelt.utils.random import set_manual_seed
from pytorch_toolbelt.utils.torch_utils import maybe_cuda, count_parameters
from torch.backends import cudnn
from torch.optim import Adam
from tqdm import tqdm

from common.dataset import get_dataloaders, read_inria_rgb
from common.factory import get_model, get_loss, get_optimizer, visualize_inria_predictions, predict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument('--fast', action='store_true')
    parser.add_argument('--fp16-opt-level', default='O1')
    parser.add_argument('--fp16-loss-scale', default=None)
    parser.add_argument('--fp16-keep-batchnorm-fp32', action='store_true')
    parser.add_argument('-dd', '--data-dir', type=str, required=True, help='Data directory for INRIA sattelite dataset')
    parser.add_argument('-m', '--model', type=str, default='unet', help='')
    parser.add_argument('-b', '--batch-size', type=int, default=8, help='Batch Size during training, e.g. -b 64')
    parser.add_argument('-e', '--epochs', type=int, default=150, help='Epoch to run')
    # parser.add_argument('-es', '--early-stopping', type=int, default=None, help='Maximum number of epochs without improvement')
    # parser.add_argument('-fe', '--freeze-encoder', type=int, default=0, help='Freeze encoder parameters for N epochs')
    # parser.add_argument('-ft', '--fine-tune', action='store_true')
    parser.add_argument('-lr', '--learning-rate', type=float, default=1e-3, help='Initial learning rate')
    parser.add_argument('-l', '--criterion', type=str, default='bce', help='Criterion')
    parser.add_argument('-o', '--optimizer', default='Adam', help='Name of the optimizer')
    parser.add_argument('-c', '--checkpoint', type=str, default=None, help='Checkpoint filename to use as initial model weights')
    parser.add_argument('-w', '--workers', default=8, type=int, help='Num workers')
    parser.add_argument('-a', '--augmentations', default='hard', type=str, help='')
    parser.add_argument('-tta', '--tta', default=None, type=str, help='Type of TTA to use [fliplr, d4]')
    parser.add_argument('-tm', '--train-mode', default='random', type=str, help='')

    args = parser.parse_args()
    set_manual_seed(args.seed)

    data_dir = args.data_dir
    num_workers = args.workers
    num_epochs = args.epochs
    batch_size = args.batch_size
    learning_rate = args.learning_rate
    model_name = args.model
    optimizer_name = args.optimizer
    image_size = (512, 512)
    fast = args.fast
    augmentations = args.augmentations
    train_mode = args.train_mode

    train_loader, valid_loader = get_dataloaders(data_dir=data_dir,
                                                 batch_size=batch_size,
                                                 num_workers=num_workers,
                                                 image_size=image_size,
                                                 augmentation=augmentations,
                                                 train_mode=train_mode,
                                                 fast=fast)

    model = maybe_cuda(get_model(model_name, image_size=image_size))
    criterion = get_loss(args.criterion)
    optimizer = get_optimizer(optimizer_name, model.parameters(), learning_rate)

    # Initialize Amp.  Amp accepts either values or strings for the optional override arguments,
    # for convenient interoperation with argparse.
    model, optimizer = amp.initialize(model, optimizer,
                                      opt_level=args.fp16_opt_level,
                                      loss_scale=args.fp16_loss_scale)
    # model, optimizer = amp.initialize(model, optimizer, opt_level="O2")
    # model, optimizer = amp.initialize(model, optimizer, opt_level="O2", keep_batchnorm_fp32=True)

    loaders = collections.OrderedDict()
    loaders["train"] = train_loader
    loaders["valid"] = valid_loader

    scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer, milestones=[10, 20, 40, 60, 90, 120], gamma=0.5)

    # model runner
    runner = SupervisedRunner()

    if args.checkpoint:
        checkpoint = UtilsFactory.load_checkpoint(fs.auto_file(args.checkpoint))
        UtilsFactory.unpack_checkpoint(checkpoint, model=model)

        checkpoint_epoch = checkpoint['epoch']
        print('Loaded model weights from', args.checkpoint)
        print('Epoch   :', checkpoint_epoch)
        print('Metrics:', checkpoint['epoch_metrics'])

    current_time = datetime.now().strftime('%b%d_%H_%M')
    prefix = f'{current_time}_{args.model}_fp16_{args.criterion}'
    log_dir = os.path.join('runs', prefix)
    os.makedirs(log_dir, exist_ok=False)

    print('Train session      :', prefix)
    print('\tFast mode      :', args.fast)
    print('\tTrain mode     :', train_mode)
    print('\tEpochs         :', num_epochs)
    print('\tWorkers        :', num_workers)
    print('\tData dir       :', data_dir)
    print('\tLog dir        :', log_dir)
    print('\tAugmentations  :', augmentations)
    print('\tTrain size     :', len(train_loader), len(train_loader.dataset))
    print('\tValid size     :', len(valid_loader), len(valid_loader.dataset))
    print('Model              :', model_name)
    print('\tParameters     :', count_parameters(model))
    print('\tImage size     :', image_size)
    print('Optimizer          :', optimizer_name)
    print('\tLearning rate  :', learning_rate)
    print('\tBatch size     :', batch_size)
    print('\tCriterion      :', args.criterion)
    print('AMP Model          :', args.fp16_opt_level)

    # model training
    runner.train(
        model=model,
        criterion=criterion,
        optimizer=optimizer,
        scheduler=scheduler,
        callbacks=[
            PixelAccuracyMetric(),
            EpochJaccardMetric(),
            ShowPolarBatchesCallback(visualize_inria_predictions, metric='accuracy', minimize=False),
        ],
        loaders=loaders,
        logdir=log_dir,
        num_epochs=num_epochs,
        verbose=True,
        main_metric='jaccard',
        minimize_metric=False,
        state_kwargs={"cmd_args": vars(args)}
    )

    best_checkpoint = UtilsFactory.load_checkpoint(fs.auto_file('best.pth', where=log_dir))
    UtilsFactory.unpack_checkpoint(best_checkpoint, model=model)

    mask = predict(model, read_inria_rgb('sample_color.jpg'), tta=args.tta, image_size=image_size, batch_size=args.batch_size, activation='sigmoid')
    mask = ((mask > 0.5) * 255).astype(np.uint8)
    name = os.path.join(log_dir, 'sample_color.jpg')
    cv2.imwrite(name, mask)

    if not args.fast:
        # Training is finished. Let's run predictions using best checkpoint weights
        out_dir = os.path.join(log_dir, 'submit')
        os.makedirs(out_dir, exist_ok=True)

        test_images = fs.find_in_dir(os.path.join(data_dir, 'test', 'images'))
        for fname in tqdm(test_images, total=len(test_images)):
            image = read_inria_rgb(fname)
            mask = predict(model, image, tta=args.tta, image_size=image_size, batch_size=args.batch_size, activation='sigmoid')
            mask = ((mask > 0.5) * 255).astype(np.uint8)
            name = os.path.join(out_dir, os.path.basename(fname))
            cv2.imwrite(name, mask)


if __name__ == '__main__':
    torch.backends.cudnn.benchmark = True
    main()
