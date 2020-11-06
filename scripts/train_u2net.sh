#export INRIA_DATA_DIR="/home/bloodaxe/datasets/AerialImageDataset"
#python -m torch.distributed.launch --nproc_per_node=4 fit_predict.py -w 6 --fp16 -v\
#  -b 6 -m b6_unet32_s2\
#  --train-mode tiles -b 8 --size 512 -s cos -o RAdam -a hard -lr 3e-4 -e 100\
#  --criterion bce 1 --criterion dice 1


export INRIA_DATA_DIR="/home/bloodaxe/datasets/AerialImageDataset"
python -m torch.distributed.launch --nproc_per_node=4 fit_predict.py -w 6 --fp16 -v\
  -b 4 -m U2NET\
  --train-mode tiles --size 512 -s cos -o RAdam -a hard -lr 3e-4 -e 50 --seed 555\
  --criterion bce 1 --criterion dice 1