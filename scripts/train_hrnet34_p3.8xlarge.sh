python fit_predict.py -m hrnet34 -b 48 -w 24 -dd /home/ubuntu/data/inria/AerialImageDataset --size 512 --train-mode tiles -s cos -o RAdam -a medium -lr 1e-3 -e 200 -d 0.1 --criterion bce 1 -v