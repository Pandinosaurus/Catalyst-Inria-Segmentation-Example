python fit_predict.py -m hrnet48 -b 32 -w 24 -dd /home/ubuntu/data/inria/AerialImageDataset --size 512 --train-mode tiles -s cos -o RAdam -a hard -lr 1e-3 -e 200 -d 0.1 --criterion bce 1 -v